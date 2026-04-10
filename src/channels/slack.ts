import { App, LogLevel } from '@slack/bolt';
import type { GenericMessageEvent, BotMessageEvent } from '@slack/types';

import { ASSISTANT_NAME, TRIGGER_PATTERN } from '../config.js';
import { updateChatName } from '../db.js';
import { readEnvFile } from '../env.js';
import { logger } from '../logger.js';
import { registerChannel, ChannelOpts } from './registry.js';
import {
  Channel,
  OnInboundMessage,
  OnChatMetadata,
  RegisteredGroup,
} from '../types.js';

// Slack's chat.postMessage API limits text to ~4000 characters per call.
// Messages exceeding this are split into sequential chunks.
const MAX_MESSAGE_LENGTH = 4000;

// The message subtypes we process. Bolt delivers all subtypes via app.event('message');
// we filter to regular messages (GenericMessageEvent, subtype undefined) and bot messages
// (BotMessageEvent, subtype 'bot_message') so we can track our own output.
type HandledMessageEvent = GenericMessageEvent | BotMessageEvent;

export interface SlackChannelOpts {
  onMessage: OnInboundMessage;
  onChatMetadata: OnChatMetadata;
  registeredGroups: () => Record<string, RegisteredGroup>;
  registerGroup: (jid: string, group: RegisteredGroup) => void;
}

export class SlackChannel implements Channel {
  name = 'slack';

  private app: App;
  private botUserId: string | undefined;
  private connected = false;
  private outgoingQueue: Array<{
    jid: string;
    text: string;
    threadTs?: string;
  }> = [];
  private flushing = false;
  private userNameCache = new Map<string, string>();
  private pendingRegistrations = new Set<string>();
  /** Stores the ts of a placeholder message per channel, so sendMessage can update it. */
  private placeholderTs = new Map<string, string>();
  /** Heartbeat intervals that update placeholders to show the bot is still working */
  private heartbeatTimers = new Map<string, ReturnType<typeof setInterval>>();
  /** Tracks threads that already received a ✅ reaction to avoid duplicates */
  private reactedThreads = new Set<string>();
  /** Active thread_ts per channel — responses go into this thread */
  private activeThreadTs = new Map<string, string>();

  private opts: SlackChannelOpts;

  constructor(opts: SlackChannelOpts) {
    this.opts = opts;

    // Read tokens from .env (not process.env — keeps secrets off the environment
    // so they don't leak to child processes, matching NanoClaw's security pattern)
    const env = readEnvFile(['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN']);
    const botToken = env.SLACK_BOT_TOKEN;
    const appToken = env.SLACK_APP_TOKEN;

    if (!botToken || !appToken) {
      throw new Error(
        'SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in .env',
      );
    }

    this.app = new App({
      token: botToken,
      appToken,
      socketMode: true,
      logLevel: LogLevel.ERROR,
    });

    this.setupEventHandlers();
  }

  private setupEventHandlers(): void {
    // Use app.event('message') instead of app.message() to capture all
    // message subtypes including bot_message (needed to track our own output)
    this.app.event('message', async ({ event }) => {
      // Bolt's event type is the full MessageEvent union (17+ subtypes).
      // We filter on subtype first, then narrow to the two types we handle.
      const subtype = (event as { subtype?: string }).subtype;
      if (subtype && subtype !== 'bot_message' && subtype !== 'file_share')
        return;

      // After filtering, event is either GenericMessageEvent or BotMessageEvent
      const msg = event as HandledMessageEvent;

      if (!msg.text) return;

      const jid = `slack:${msg.channel}`;
      const timestamp = new Date(parseFloat(msg.ts) * 1000).toISOString();
      const isGroup = msg.channel_type !== 'im';

      // Always report metadata for group discovery
      this.opts.onChatMetadata(jid, timestamp, undefined, 'slack', isGroup);

      // Only deliver full messages for registered groups.
      // If the channel is not registered but the bot was @mentioned (or it's a DM),
      // auto-register so users can invoke the bot from any channel it's been invited to.
      const groups = this.opts.registeredGroups();
      if (!groups[jid]) {
        const isBotMentioned =
          this.botUserId && msg.text.includes(`<@${this.botUserId}>`);
        const isDm = msg.channel_type === 'im';
        if (!isBotMentioned && !isDm) return;

        if (this.pendingRegistrations.has(jid)) return;
        this.pendingRegistrations.add(jid);

        const folderName = `slack_${msg.channel}`;
        const channelName = isDm
          ? 'Slack DM'
          : await this.resolveChannelName(msg.channel);
        this.opts.registerGroup(jid, {
          name: channelName,
          folder: folderName,
          trigger: `@${ASSISTANT_NAME}`,
          added_at: new Date().toISOString(),
          requiresTrigger: !isDm,
          isMain: false,
        });
        this.pendingRegistrations.delete(jid);
        logger.info(
          { jid, folder: folderName, isDm, channelName },
          'Auto-registered Slack channel on bot mention',
        );
      }

      const isBotMessage = !!msg.bot_id || msg.user === this.botUserId;

      let senderName: string;
      if (isBotMessage) {
        senderName = ASSISTANT_NAME;
      } else {
        senderName =
          (msg.user ? await this.resolveUserName(msg.user) : undefined) ||
          msg.user ||
          'unknown';
      }

      // Translate Slack <@UBOTID> mentions into TRIGGER_PATTERN format.
      // Slack encodes @mentions as <@U12345>, which won't match TRIGGER_PATTERN
      // (e.g., ^@<ASSISTANT_NAME>\b), so we prepend the trigger when the bot is @mentioned.
      let content = msg.text;
      const isBotMentionedHere =
        !!this.botUserId &&
        !isBotMessage &&
        msg.text.includes(`<@${this.botUserId}>`);
      if (isBotMentionedHere) {
        if (!TRIGGER_PATTERN.test(content)) {
          content = `@${ASSISTANT_NAME} ${content}`;
        }
        // Thread context is set by index.ts via setThreadContext before
        // sendMessage/setTyping — not here, to avoid race conditions when
        // multiple threads trigger concurrently.
      }

      // thread_id for session isolation:
      // - In a thread: msg.thread_ts (parent message ts)
      // - Top-level bot mention in group: msg.ts (starts new thread)
      // - DM: msg.thread_ts || msg.ts (every message gets a thread)
      // - Non-mention group message outside thread: undefined
      const threadId = isGroup
        ? msg.thread_ts || (isBotMentionedHere ? msg.ts : undefined)
        : msg.thread_ts || msg.ts;

      this.opts.onMessage(jid, {
        id: msg.ts,
        chat_jid: jid,
        sender: msg.user || msg.bot_id || '',
        sender_name: senderName,
        content,
        timestamp,
        is_from_me: isBotMessage,
        is_bot_message: isBotMessage,
        thread_id: threadId,
      });
    });
  }

  async connect(): Promise<void> {
    await this.app.start();

    // Get bot's own user ID for self-message detection.
    // Resolve this BEFORE setting connected=true so that messages arriving
    // during startup can correctly detect bot-sent messages.
    try {
      const auth = await this.app.client.auth.test();
      this.botUserId = auth.user_id as string;
      logger.info({ botUserId: this.botUserId }, 'Connected to Slack');
    } catch (err) {
      logger.warn({ err }, 'Connected to Slack but failed to get bot user ID');
    }

    this.connected = true;

    // Flush any messages queued before connection
    await this.flushOutgoingQueue();

    // Sync channel names on startup
    await this.syncChannelMetadata();
  }

  async sendMessage(
    jid: string,
    text: string,
    threadId?: string,
  ): Promise<void> {
    const channelId = jid.replace(/^slack:/, '');
    const threadTs = threadId || this.activeThreadTs.get(jid);
    const placeholderKey = threadTs ? `${jid}:${threadTs}` : jid;

    if (!this.connected) {
      this.outgoingQueue.push({ jid, text, threadTs });
      logger.info(
        { jid, queueSize: this.outgoingQueue.length },
        'Slack disconnected, message queued',
      );
      return;
    }

    try {
      const placeholderTs = this.placeholderTs.get(placeholderKey);

      if (placeholderTs && text.length <= MAX_MESSAGE_LENGTH) {
        this.clearHeartbeat(placeholderKey);
        this.placeholderTs.delete(placeholderKey);
        await this.app.client.chat.update({
          channel: channelId,
          ts: placeholderTs,
          text,
        });
      } else {
        if (placeholderTs) {
          this.clearHeartbeat(placeholderKey);
          this.placeholderTs.delete(placeholderKey);
          await this.app.client.chat
            .delete({ channel: channelId, ts: placeholderTs })
            .catch(() => {});
        }
        if (text.length <= MAX_MESSAGE_LENGTH) {
          await this.app.client.chat.postMessage({
            channel: channelId,
            text,
            ...(threadTs && { thread_ts: threadTs }),
          });
        } else {
          for (let i = 0; i < text.length; i += MAX_MESSAGE_LENGTH) {
            await this.app.client.chat.postMessage({
              channel: channelId,
              text: text.slice(i, i + MAX_MESSAGE_LENGTH),
              ...(threadTs && { thread_ts: threadTs }),
            });
          }
        }
      }
      logger.info({ jid, length: text.length, threadTs }, 'Slack message sent');
      // React with ✅ on the triggering message after sending the first response
      const reactKey = `${channelId}:${threadTs}`;
      if (threadTs && !this.reactedThreads.has(reactKey)) {
        this.reactedThreads.add(reactKey);
        this.addReaction(channelId, 'white_check_mark', threadTs);
      }
    } catch (err) {
      this.clearHeartbeat(placeholderKey);
      this.placeholderTs.delete(placeholderKey);
      this.outgoingQueue.push({ jid, text, threadTs });
      logger.warn(
        { jid, err, queueSize: this.outgoingQueue.length },
        'Failed to send Slack message, queued',
      );
    }
  }

  isConnected(): boolean {
    return this.connected;
  }

  ownsJid(jid: string): boolean {
    return jid.startsWith('slack:');
  }

  setThreadContext(jid: string, threadId: string | undefined): void {
    if (threadId) {
      this.activeThreadTs.set(jid, threadId);
    } else {
      this.activeThreadTs.delete(jid);
    }
  }

  async disconnect(): Promise<void> {
    this.connected = false;
    for (const key of this.heartbeatTimers.keys()) {
      this.clearHeartbeat(key);
    }
    await this.app.stop();
  }

  /** Emoji sequence for heartbeat updates (30s intervals, up to ~10 min) */
  private static readonly HEARTBEAT_EMOJIS = [
    ':muscle:',
    ':fire:',
    ':zap:',
    ':boom:',
    ':star2:',
    ':ocean:',
    ':wind_blowing_face:',
    ':cyclone:',
    ':volcano:',
    ':comet:',
    ':dizzy:',
    ':sparkles:',
    ':crown:',
    ':skull_and_crossbones:',
    ':crossed_swords:',
    ':anchor:',
    ':pirate_flag:',
    ':trophy:',
    ':rainbow:',
    ':rocket:',
  ];

  private static readonly PLACEHOLDER_BASE =
    ':meat_on_bone::dash: ゴムゴムの〜 ...';

  private clearHeartbeat(placeholderKey: string): void {
    const timer = this.heartbeatTimers.get(placeholderKey);
    if (timer) {
      clearInterval(timer);
      this.heartbeatTimers.delete(placeholderKey);
    }
  }

  async setTyping(
    jid: string,
    isTyping: boolean,
    threadId?: string,
  ): Promise<void> {
    const channelId = jid.replace(/^slack:/, '');
    const threadTs = threadId || this.activeThreadTs.get(jid);
    const placeholderKey = threadTs ? `${jid}:${threadTs}` : jid;
    if (isTyping) {
      // React with 👀 on the triggering message to show we're looking at it
      if (threadTs) {
        this.addReaction(channelId, 'eyes', threadTs);
      }
      try {
        const res = await this.app.client.chat.postMessage({
          channel: channelId,
          text: SlackChannel.PLACEHOLDER_BASE,
          ...(threadTs && { thread_ts: threadTs }),
        });
        if (res.ts) {
          this.placeholderTs.set(placeholderKey, res.ts);
          this.clearHeartbeat(placeholderKey);

          let tick = 0;
          const timer = setInterval(async () => {
            const ts = this.placeholderTs.get(placeholderKey);
            if (!ts) {
              this.clearHeartbeat(placeholderKey);
              return;
            }
            tick++;
            const emojiCount = Math.min(
              tick,
              SlackChannel.HEARTBEAT_EMOJIS.length,
            );
            const emojis = SlackChannel.HEARTBEAT_EMOJIS.slice(
              0,
              emojiCount,
            ).join('');
            const elapsed =
              tick > SlackChannel.HEARTBEAT_EMOJIS.length
                ? ` (${Math.floor((tick * 30) / 60)}분 경과)`
                : '';
            try {
              await this.app.client.chat.update({
                channel: channelId,
                ts,
                text: `${SlackChannel.PLACEHOLDER_BASE} ${emojis}${elapsed}`,
              });
            } catch {
              this.clearHeartbeat(placeholderKey);
            }
          }, 30_000);
          this.heartbeatTimers.set(placeholderKey, timer);
        }
      } catch (err) {
        logger.debug({ jid, err }, 'Failed to post Slack placeholder');
      }
    } else {
      this.clearHeartbeat(placeholderKey);
      this.reactedThreads.delete(`${channelId}:${threadTs}`);
      const ts = this.placeholderTs.get(placeholderKey);
      if (ts) {
        this.placeholderTs.delete(placeholderKey);
        try {
          await this.app.client.chat.delete({ channel: channelId, ts });
        } catch {
          // Already updated or deleted — ignore
        }
      }
    }
  }

  private async addReaction(
    channel: string,
    name: string,
    timestamp: string,
  ): Promise<void> {
    try {
      await this.app.client.reactions.add({ channel, name, timestamp });
    } catch (err) {
      logger.warn({ channel, name, timestamp, err }, 'Failed to add reaction');
    }
  }

  /**
   * Sync channel metadata from Slack.
   * Fetches channels the bot is a member of and stores their names in the DB.
   */
  async syncChannelMetadata(): Promise<void> {
    try {
      logger.info('Syncing channel metadata from Slack...');
      let cursor: string | undefined;
      let count = 0;

      do {
        const result = await this.app.client.conversations.list({
          types: 'public_channel,private_channel',
          exclude_archived: true,
          limit: 200,
          cursor,
        });

        for (const ch of result.channels || []) {
          if (ch.id && ch.name && ch.is_member) {
            updateChatName(`slack:${ch.id}`, ch.name);
            count++;
          }
        }

        cursor = result.response_metadata?.next_cursor || undefined;
      } while (cursor);

      logger.info({ count }, 'Slack channel metadata synced');
    } catch (err) {
      logger.error({ err }, 'Failed to sync Slack channel metadata');
    }
  }

  private async resolveChannelName(channelId: string): Promise<string> {
    try {
      const result = await this.app.client.conversations.info({
        channel: channelId,
      });
      return result.channel?.name
        ? `Slack #${result.channel.name}`
        : `Slack #${channelId}`;
    } catch {
      return `Slack #${channelId}`;
    }
  }

  private async resolveUserName(userId: string): Promise<string | undefined> {
    if (!userId) return undefined;

    const cached = this.userNameCache.get(userId);
    if (cached) return cached;

    try {
      const result = await this.app.client.users.info({ user: userId });
      const name = result.user?.real_name || result.user?.name;
      if (name) this.userNameCache.set(userId, name);
      return name;
    } catch (err) {
      logger.debug({ userId, err }, 'Failed to resolve Slack user name');
      return undefined;
    }
  }

  private async flushOutgoingQueue(): Promise<void> {
    if (this.flushing || this.outgoingQueue.length === 0) return;
    this.flushing = true;
    try {
      logger.info(
        { count: this.outgoingQueue.length },
        'Flushing Slack outgoing queue',
      );
      while (this.outgoingQueue.length > 0) {
        const item = this.outgoingQueue.shift()!;
        const channelId = item.jid.replace(/^slack:/, '');
        await this.app.client.chat.postMessage({
          channel: channelId,
          text: item.text,
          ...(item.threadTs && { thread_ts: item.threadTs }),
        });
        logger.info(
          { jid: item.jid, length: item.text.length },
          'Queued Slack message sent',
        );
      }
    } finally {
      this.flushing = false;
    }
  }
}

registerChannel('slack', (opts: ChannelOpts) => {
  const envVars = readEnvFile(['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN']);
  if (!envVars.SLACK_BOT_TOKEN || !envVars.SLACK_APP_TOKEN) {
    logger.warn('Slack: SLACK_BOT_TOKEN or SLACK_APP_TOKEN not set');
    return null;
  }
  return new SlackChannel(opts);
});
