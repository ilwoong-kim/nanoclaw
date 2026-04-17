import { ChildProcess } from 'child_process';
import fs from 'fs';
import path from 'path';

import { MAX_CONCURRENT_CONTAINERS } from './config.js';
import { resolveThreadIpcPath } from './group-folder.js';
import { logger } from './logger.js';

interface QueuedTask {
  id: string;
  groupJid: string;
  fn: () => Promise<void>;
}

const MAX_RETRIES = 5;
const BASE_RETRY_MS = 5000;

function queueKey(groupJid: string, threadId?: string): string {
  return threadId ? `${groupJid}:thread:${threadId}` : groupJid;
}

function parseQueueKey(key: string): {
  groupJid: string;
  threadId?: string;
} {
  const marker = ':thread:';
  const idx = key.indexOf(marker);
  if (idx === -1) return { groupJid: key };
  return {
    groupJid: key.slice(0, idx),
    threadId: key.slice(idx + marker.length),
  };
}

interface GroupState {
  active: boolean;
  idleWaiting: boolean;
  isTaskContainer: boolean;
  runningTaskId: string | null;
  pendingMessages: boolean;
  pendingTasks: QueuedTask[];
  process: ChildProcess | null;
  containerName: string | null;
  groupFolder: string | null;
  retryCount: number;
}

export class GroupQueue {
  private groups = new Map<string, GroupState>();
  private activeCount = 0;
  private waitingGroups: string[] = [];
  private processMessagesFn:
    | ((groupJid: string, threadId?: string) => Promise<boolean>)
    | null = null;
  private shuttingDown = false;

  private getGroup(key: string): GroupState {
    let state = this.groups.get(key);
    if (!state) {
      state = {
        active: false,
        idleWaiting: false,
        isTaskContainer: false,
        runningTaskId: null,
        pendingMessages: false,
        pendingTasks: [],
        process: null,
        containerName: null,
        groupFolder: null,
        retryCount: 0,
      };
      this.groups.set(key, state);
    }
    return state;
  }

  setProcessMessagesFn(
    fn: (groupJid: string, threadId?: string) => Promise<boolean>,
  ): void {
    this.processMessagesFn = fn;
  }

  enqueueMessageCheck(groupJid: string, threadId?: string): void {
    if (this.shuttingDown) return;

    const key = queueKey(groupJid, threadId);
    const state = this.getGroup(key);

    if (state.active) {
      state.pendingMessages = true;
      logger.debug({ groupJid, threadId }, 'Container active, message queued');
      return;
    }

    if (this.activeCount >= MAX_CONCURRENT_CONTAINERS) {
      state.pendingMessages = true;
      if (!this.waitingGroups.includes(key)) {
        this.waitingGroups.push(key);
      }
      logger.debug(
        { groupJid, threadId, activeCount: this.activeCount },
        'At concurrency limit, message queued',
      );
      return;
    }

    this.runForGroup(key, 'messages').catch((err) =>
      logger.error(
        { groupJid, threadId, err },
        'Unhandled error in runForGroup',
      ),
    );
  }

  enqueueTask(groupJid: string, taskId: string, fn: () => Promise<void>): void {
    if (this.shuttingDown) return;

    const key = groupJid;
    const state = this.getGroup(key);

    // Prevent double-queuing: check both pending and currently-running task
    if (state.runningTaskId === taskId) {
      logger.debug({ groupJid, taskId }, 'Task already running, skipping');
      return;
    }
    if (state.pendingTasks.some((t) => t.id === taskId)) {
      logger.debug({ groupJid, taskId }, 'Task already queued, skipping');
      return;
    }

    if (state.active) {
      state.pendingTasks.push({ id: taskId, groupJid, fn });
      if (state.idleWaiting) {
        this.closeStdin(groupJid);
      }
      logger.debug({ groupJid, taskId }, 'Container active, task queued');
      return;
    }

    if (this.activeCount >= MAX_CONCURRENT_CONTAINERS) {
      state.pendingTasks.push({ id: taskId, groupJid, fn });
      if (!this.waitingGroups.includes(key)) {
        this.waitingGroups.push(key);
      }
      logger.debug(
        { groupJid, taskId, activeCount: this.activeCount },
        'At concurrency limit, task queued',
      );
      return;
    }

    // Run immediately
    this.runTask(key, { id: taskId, groupJid, fn }).catch((err) =>
      logger.error({ groupJid, taskId, err }, 'Unhandled error in runTask'),
    );
  }

  registerProcess(
    groupJid: string,
    proc: ChildProcess,
    containerName: string,
    groupFolder?: string,
    threadId?: string,
  ): void {
    const key = queueKey(groupJid, threadId);
    const state = this.getGroup(key);
    state.process = proc;
    state.containerName = containerName;
    if (groupFolder) state.groupFolder = groupFolder;
  }

  /**
   * Mark the container as idle-waiting (finished work, waiting for IPC input).
   * If tasks are pending, preempt the idle container immediately.
   */
  notifyIdle(groupJid: string, threadId?: string): void {
    const key = queueKey(groupJid, threadId);
    const state = this.getGroup(key);
    state.idleWaiting = true;
    if (state.pendingTasks.length > 0) {
      this.closeStdin(groupJid, threadId);
    }
  }

  /**
   * Send a follow-up message to the active container via IPC file.
   * Returns true if the message was written, false if no active container.
   */
  sendMessage(
    groupJid: string,
    text: string,
    threadId?: string,
    imagePaths?: string[],
  ): boolean {
    const key = queueKey(groupJid, threadId);
    const state = this.getGroup(key);
    if (!state.active || !state.groupFolder || state.isTaskContainer)
      return false;
    state.idleWaiting = false; // Agent is about to receive work, no longer idle

    const ipcDir = resolveThreadIpcPath(state.groupFolder, threadId);
    const inputDir = path.join(ipcDir, 'input');
    try {
      fs.mkdirSync(inputDir, { recursive: true });
      const filename = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}.json`;
      const filepath = path.join(inputDir, filename);
      const tempPath = `${filepath}.tmp`;
      const payload: { type: string; text: string; imagePaths?: string[] } = {
        type: 'message',
        text,
      };
      if (imagePaths && imagePaths.length > 0) {
        payload.imagePaths = imagePaths;
      }
      fs.writeFileSync(tempPath, JSON.stringify(payload));
      fs.renameSync(tempPath, filepath);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Signal the active container to wind down by writing a close sentinel.
   */
  closeStdin(groupJid: string, threadId?: string): void {
    const key = queueKey(groupJid, threadId);
    const state = this.getGroup(key);
    if (!state.active || !state.groupFolder) return;

    const ipcDir = resolveThreadIpcPath(state.groupFolder, threadId);
    const inputDir = path.join(ipcDir, 'input');
    try {
      fs.mkdirSync(inputDir, { recursive: true });
      fs.writeFileSync(path.join(inputDir, '_close'), '');
    } catch {
      // ignore
    }
  }

  /**
   * Force-clear the group state so the next message spawns a new container.
   * The old container will still wind down via _close sentinel.
   * Note: activeCount is NOT decremented here — runForGroup/runTask's finally
   * block handles that when the container actually exits.
   */
  clearSession(groupJid: string, threadId?: string): void {
    this.closeStdin(groupJid, threadId);
    const key = queueKey(groupJid, threadId);
    const state = this.getGroup(key);
    state.idleWaiting = false;
    state.groupFolder = null;
  }

  private async runForGroup(
    key: string,
    reason: 'messages' | 'drain',
  ): Promise<void> {
    const state = this.getGroup(key);
    const { groupJid, threadId } = parseQueueKey(key);
    state.active = true;
    state.idleWaiting = false;
    state.isTaskContainer = false;
    state.pendingMessages = false;
    this.activeCount++;

    logger.debug(
      { groupJid, threadId, reason, activeCount: this.activeCount },
      'Starting container for group',
    );

    try {
      if (this.processMessagesFn) {
        const success = await this.processMessagesFn(groupJid, threadId);
        if (success) {
          state.retryCount = 0;
        } else {
          this.scheduleRetry(key, state);
        }
      }
    } catch (err) {
      logger.error(
        { groupJid, threadId, err },
        'Error processing messages for group',
      );
      this.scheduleRetry(key, state);
    } finally {
      state.active = false;
      state.process = null;
      state.containerName = null;
      state.groupFolder = null;

      this.activeCount--;
      this.drainGroup(key);
    }
  }

  private async runTask(key: string, task: QueuedTask): Promise<void> {
    const state = this.getGroup(key);
    state.active = true;
    state.idleWaiting = false;
    state.isTaskContainer = true;
    state.runningTaskId = task.id;
    this.activeCount++;

    const { groupJid } = parseQueueKey(key);
    logger.debug(
      { groupJid, taskId: task.id, activeCount: this.activeCount },
      'Running queued task',
    );

    try {
      await task.fn();
    } catch (err) {
      logger.error({ groupJid, taskId: task.id, err }, 'Error running task');
    } finally {
      state.active = false;
      state.isTaskContainer = false;
      state.runningTaskId = null;

      state.process = null;
      state.containerName = null;
      state.groupFolder = null;
      this.activeCount--;
      this.drainGroup(key);
    }
  }

  private scheduleRetry(key: string, state: GroupState): void {
    state.retryCount++;
    const { groupJid, threadId } = parseQueueKey(key);
    if (state.retryCount > MAX_RETRIES) {
      logger.error(
        { groupJid, threadId, retryCount: state.retryCount },
        'Max retries exceeded, dropping messages (will retry on next incoming message)',
      );
      state.retryCount = 0;
      return;
    }

    const delayMs = BASE_RETRY_MS * Math.pow(2, state.retryCount - 1);
    logger.info(
      { groupJid, threadId, retryCount: state.retryCount, delayMs },
      'Scheduling retry with backoff',
    );
    setTimeout(() => {
      if (!this.shuttingDown) {
        this.enqueueMessageCheck(groupJid, threadId);
      }
    }, delayMs);
  }

  private drainGroup(key: string): void {
    if (this.shuttingDown) return;

    const state = this.getGroup(key);

    // Tasks first (they won't be re-discovered from SQLite like messages)
    if (state.pendingTasks.length > 0) {
      const task = state.pendingTasks.shift()!;
      this.runTask(key, task).catch((err) =>
        logger.error(
          { key, taskId: task.id, err },
          'Unhandled error in runTask (drain)',
        ),
      );
      return;
    }

    // Then pending messages
    if (state.pendingMessages) {
      this.runForGroup(key, 'drain').catch((err) =>
        logger.error({ key, err }, 'Unhandled error in runForGroup (drain)'),
      );
      return;
    }

    // Evict stale state to prevent unbounded Map growth
    // Keep entries with pending retries so retryCount is preserved
    if (state.retryCount === 0) {
      this.groups.delete(key);
    }

    this.drainWaiting();
  }

  private drainWaiting(): void {
    while (
      this.waitingGroups.length > 0 &&
      this.activeCount < MAX_CONCURRENT_CONTAINERS
    ) {
      const nextKey = this.waitingGroups.shift()!;
      const state = this.getGroup(nextKey);

      // Prioritize tasks over messages
      if (state.pendingTasks.length > 0) {
        const task = state.pendingTasks.shift()!;
        this.runTask(nextKey, task).catch((err) =>
          logger.error(
            { key: nextKey, taskId: task.id, err },
            'Unhandled error in runTask (waiting)',
          ),
        );
      } else if (state.pendingMessages) {
        this.runForGroup(nextKey, 'drain').catch((err) =>
          logger.error(
            { key: nextKey, err },
            'Unhandled error in runForGroup (waiting)',
          ),
        );
      }
      // If neither pending, skip this key
    }
  }

  async shutdown(_gracePeriodMs: number): Promise<void> {
    this.shuttingDown = true;

    // Count active containers but don't kill them — they'll finish on their own
    // via idle timeout or container timeout. The --rm flag cleans them up on exit.
    // This prevents WhatsApp reconnection restarts from killing working agents.
    const activeContainers: string[] = [];
    for (const [_key, state] of this.groups) {
      if (state.process && !state.process.killed && state.containerName) {
        activeContainers.push(state.containerName);
      }
    }

    logger.info(
      { activeCount: this.activeCount, detachedContainers: activeContainers },
      'GroupQueue shutting down (containers detached, not killed)',
    );
  }
}
