import { execFile } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';

import { logger } from './logger.js';
import { RegisteredGroup } from './types.js';

const execFileAsync = promisify(execFile);

const DEFAULT_INTERVAL_MS = 10 * 60 * 1000;
const MAX_DEPTH = 3;
const PULL_TIMEOUT_MS = 60_000;
const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  'dist',
  'build',
  '.next',
  '.venv',
  'venv',
  '__pycache__',
  '.cache',
]);

function expandPath(p: string): string {
  if (p.startsWith('~')) return path.join(os.homedir(), p.slice(1));
  return p;
}

function hasGitDir(entries: fs.Dirent[]): boolean {
  return entries.some((e) => e.name === '.git');
}

function walkForGitDirs(root: string, maxDepth: number): string[] {
  const results: string[] = [];

  function walk(dir: string, depth: number): void {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    if (hasGitDir(entries)) {
      results.push(dir);
      return;
    }
    if (depth >= maxDepth) return;
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      if (SKIP_DIRS.has(e.name)) continue;
      if (e.name.startsWith('.')) continue;
      walk(path.join(dir, e.name), depth + 1);
    }
  }

  walk(root, 0);
  return results;
}

export function collectRepoPaths(
  groups: Record<string, RegisteredGroup>,
  maxDepth: number = MAX_DEPTH,
): string[] {
  const hostRoots = new Set<string>();
  for (const group of Object.values(groups)) {
    for (const mount of group.containerConfig?.additionalMounts ?? []) {
      hostRoots.add(expandPath(mount.hostPath));
    }
  }
  const repos = new Set<string>();
  for (const root of hostRoots) {
    try {
      if (!fs.statSync(root).isDirectory()) continue;
    } catch {
      continue;
    }
    for (const r of walkForGitDirs(root, maxDepth)) repos.add(r);
  }
  return [...repos].sort();
}

type PullResult =
  | { status: 'updated'; before: string; after: string }
  | { status: 'up-to-date' }
  | { status: 'skipped'; reason: string }
  | { status: 'failed'; reason: string };

async function runGit(repoPath: string, args: string[]): Promise<string> {
  const env = { ...process.env, GIT_TERMINAL_PROMPT: '0' };
  const { stdout } = await execFileAsync('git', ['-C', repoPath, ...args], {
    env,
    timeout: PULL_TIMEOUT_MS,
  });
  return stdout.trim();
}

export async function pullRepo(repoPath: string): Promise<PullResult> {
  let statusOut: string;
  try {
    statusOut = await runGit(repoPath, ['status', '--porcelain']);
  } catch (err) {
    return { status: 'failed', reason: `status: ${(err as Error).message.split('\n')[0]}` };
  }
  if (statusOut) return { status: 'skipped', reason: 'dirty' };

  let before = '';
  try {
    before = await runGit(repoPath, ['rev-parse', 'HEAD']);
  } catch {
    return { status: 'skipped', reason: 'no-head' };
  }

  try {
    await runGit(repoPath, ['pull', '--ff-only', '--quiet']);
  } catch (err) {
    return {
      status: 'failed',
      reason: (err as Error).message.split('\n')[0].slice(0, 200),
    };
  }

  let after = before;
  try {
    after = await runGit(repoPath, ['rev-parse', 'HEAD']);
  } catch {
    /* non-fatal */
  }

  if (after === before) return { status: 'up-to-date' };
  return { status: 'updated', before, after };
}

let syncInFlight = false;
let syncTimer: ReturnType<typeof setInterval> | null = null;

async function runSync(
  getGroups: () => Record<string, RegisteredGroup>,
): Promise<void> {
  if (syncInFlight) {
    logger.debug('Repo sync already in flight, skipping this tick');
    return;
  }
  syncInFlight = true;
  try {
    const repos = collectRepoPaths(getGroups());
    if (repos.length === 0) {
      logger.debug('No repos discovered for sync');
      return;
    }
    let updated = 0;
    let skipped = 0;
    let failed = 0;
    for (const repo of repos) {
      const result = await pullRepo(repo);
      switch (result.status) {
        case 'updated':
          updated++;
          logger.info(
            {
              repo,
              before: result.before.slice(0, 8),
              after: result.after.slice(0, 8),
            },
            'Repo updated via pull',
          );
          break;
        case 'up-to-date':
          logger.debug({ repo }, 'Repo up-to-date');
          break;
        case 'skipped':
          skipped++;
          logger.debug({ repo, reason: result.reason }, 'Repo pull skipped');
          break;
        case 'failed':
          failed++;
          logger.warn({ repo, reason: result.reason }, 'Repo pull failed');
          break;
      }
    }
    logger.info(
      { total: repos.length, updated, skipped, failed },
      'Repo sync complete',
    );
  } finally {
    syncInFlight = false;
  }
}

export function startRepoSync(
  getGroups: () => Record<string, RegisteredGroup>,
  intervalMs: number = DEFAULT_INTERVAL_MS,
): void {
  if (syncTimer) return;
  runSync(getGroups).catch((err) =>
    logger.error({ err }, 'Initial repo sync failed'),
  );
  syncTimer = setInterval(() => {
    runSync(getGroups).catch((err) =>
      logger.error({ err }, 'Scheduled repo sync failed'),
    );
  }, intervalMs);
  syncTimer.unref?.();
}

export function stopRepoSync(): void {
  if (syncTimer) {
    clearInterval(syncTimer);
    syncTimer = null;
  }
}
