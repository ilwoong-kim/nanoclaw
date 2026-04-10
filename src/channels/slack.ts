import { App, LogLevel } from '@slack/bolt';
import type { GenericMessageEvent, BotMessageEvent } from '@slack/types';

import fs from 'fs';
import path from 'path';

import { ASSISTANT_NAME, TRIGGER_PATTERN } from '../config.js';
import { updateChatName } from '../db.js';
import { readEnvFile } from '../env.js';
import { resolveGroupFolderPath } from '../group-folder.js';
import { processImage } from '../image.js';
import { logger } from '../logger.js';
import { registerChannel, ChannelOpts } from './registry.js';
import {
  Channel,
  ImageAttachment,
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
  /** Tracks messages that already received a ✅ reaction to avoid duplicates */
  private reactedMessages = new Set<string>();
  /** Maps stateKey → trigger message timestamp for reaction targeting */
  private triggerMessageIds = new Map<string, string>();
  /** Active thread_ts per channel — responses go into this thread */
  private activeThreadTs = new Map<string, string>();

  private opts: SlackChannelOpts;
  private botToken: string;
  private userToken: string | undefined;

  constructor(opts: SlackChannelOpts) {
    this.opts = opts;

    // Read tokens from .env (not process.env — keeps secrets off the environment
    // so they don't leak to child processes, matching NanoClaw's security pattern)
    const env = readEnvFile([
      'SLACK_BOT_TOKEN',
      'SLACK_APP_TOKEN',
      'SLACK_USER_TOKEN',
    ]);
    const botToken = env.SLACK_BOT_TOKEN;
    const appToken = env.SLACK_APP_TOKEN;

    if (!botToken || !appToken) {
      throw new Error(
        'SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in .env',
      );
    }

    this.botToken = botToken;
    this.userToken = env.SLACK_USER_TOKEN;
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

      // Extract image files from file_share events
      const files = (msg as any).files as
        | Array<{
            id: string;
            name?: string;
            mimetype?: string;
            url_private_download?: string;
          }>
        | undefined;
      const imageFiles =
        files?.filter((f) => f.mimetype?.startsWith('image/')) ?? [];

      // Allow through if there's text OR image files
      if (!msg.text && imageFiles.length === 0) return;

      const jid = `slack:${msg.channel}`;
      const timestamp = new Date(parseFloat(msg.ts) * 1000).toISOString();
      const isGroup = msg.channel_type !== 'im';

      // Always report metadata for group discovery
      this.opts.onChatMetadata(jid, timestamp, undefined, 'slack', isGroup);

      // Only deliver full messages for registered groups.
      // If the channel is not registered but the bot was @mentioned (or it's a DM),
      // auto-register so users can invoke the bot from any channel it's been invited to.
      const groups = this.opts.registeredGroups();
      const mentionText = msg.text || '';
      if (!groups[jid]) {
        const isBotMentioned =
          this.botUserId && mentionText.includes(`<@${this.botUserId}>`);
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
      let content = msg.text || '';
      const isBotMentionedHere =
        !!this.botUserId &&
        !isBotMessage &&
        mentionText.includes(`<@${this.botUserId}>`);
      if (isBotMentionedHere) {
        if (!TRIGGER_PATTERN.test(content)) {
          content = `@${ASSISTANT_NAME} ${content}`;
        }
      }

      // Download and process image files
      let images: ImageAttachment[] | undefined;
      if (imageFiles.length > 0 && !isBotMessage) {
        const group = groups[jid];
        if (group) {
          images = await this.processSlackImages(imageFiles, group.folder);
          // Add image references to text content for fallback
          for (const img of images) {
            content += ` [Image: ${img.filename}] (${img.path})`;
          }
        }
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
        images,
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
      const stateKey = `${channelId}:${threadTs || ''}`;
      const triggerMsgTs = this.triggerMessageIds.get(stateKey) || threadTs;
      if (triggerMsgTs) {
        const reactKey = `${channelId}:${triggerMsgTs}`;
        if (!this.reactedMessages.has(reactKey)) {
          this.reactedMessages.add(reactKey);
          this.addReaction(channelId, 'white_check_mark', triggerMsgTs);
        }
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
    this.reactedMessages.clear();
    this.triggerMessageIds.clear();
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
    triggerMessageId?: string,
  ): Promise<void> {
    const channelId = jid.replace(/^slack:/, '');
    const threadTs = threadId || this.activeThreadTs.get(jid);
    const placeholderKey = threadTs ? `${jid}:${threadTs}` : jid;
    const stateKey = `${channelId}:${threadTs || ''}`;
    if (isTyping) {
      // Store trigger message ID for reaction targeting
      if (triggerMessageId) {
        // Cap to prevent unbounded growth on error paths where setTyping(false) never fires
        if (this.triggerMessageIds.size > 500) this.triggerMessageIds.clear();
        if (this.reactedMessages.size > 500) this.reactedMessages.clear();
        this.triggerMessageIds.set(stateKey, triggerMessageId);
      }
      // React with 👀 on the triggering message to show we're looking at it
      const reactionTs = triggerMessageId || threadTs;
      if (reactionTs) {
        this.addReaction(channelId, 'eyes', reactionTs);
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
      const storedMsgTs = this.triggerMessageIds.get(stateKey);
      this.reactedMessages.delete(`${channelId}:${storedMsgTs || threadTs}`);
      this.triggerMessageIds.delete(stateKey);
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

  /**
   * Download a Slack file using authenticated URL.
   */
  private async downloadSlackFile(
    fileUrl: string,
    groupFolder: string,
    filename: string,
  ): Promise<{ containerPath: string; hostPath: string } | null> {
    try {
      const groupDir = resolveGroupFolderPath(groupFolder);
      const attachDir = path.join(groupDir, 'attachments');
      fs.mkdirSync(attachDir, { recursive: true });

      const safeName = filename.replace(/[^a-zA-Z0-9._-]/g, '_');
      const destPath = path.join(attachDir, safeName);

      // Prefer user token for file downloads — bot tokens often get HTML login pages
      const token = this.userToken || this.botToken;
      const resp = await fetch(fileUrl, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        logger.warn(
          { fileUrl, status: resp.status },
          'Slack file download failed',
        );
        return null;
      }

      // Verify we got an image, not an HTML login page
      const contentType = resp.headers.get('content-type') || '';
      if (contentType.includes('text/html')) {
        logger.warn(
          { fileUrl, contentType },
          'Slack file download returned HTML — token may lack files:read scope',
        );
        return null;
      }

      const buffer = Buffer.from(await resp.arrayBuffer());
      fs.writeFileSync(destPath, buffer);

      logger.info({ filename: safeName }, 'Slack file downloaded');
      return {
        containerPath: `/workspace/group/attachments/${safeName}`,
        hostPath: destPath,
      };
    } catch (err) {
      logger.error({ err, filename }, 'Failed to download Slack file');
      return null;
    }
  }

  /**
   * Download and process Slack image files for vision.
   */
  private async processSlackImages(
    imageFiles: Array<{
      id: string;
      name?: string;
      mimetype?: string;
      url_private_download?: string;
    }>,
    groupFolder: string,
  ): Promise<ImageAttachment[]> {
    const groupDir = resolveGroupFolderPath(groupFolder);
    const attachDir = path.join(groupDir, 'attachments');

    const settled = await Promise.all(
      imageFiles.map(async (file): Promise<ImageAttachment | null> => {
        let downloadUrl = file.url_private_download;
        if (!downloadUrl) {
          try {
            const info = await this.app.client.files.info({ file: file.id });
            downloadUrl = (info.file as any)?.url_private_download;
          } catch (err) {
            logger.warn(
              { fileId: file.id, err },
              'Failed to get Slack file info',
            );
            return null;
          }
        }
        if (!downloadUrl) return null;

        const filename =
          file.name ||
          `slack_image_${file.id}.${file.mimetype?.split('/')[1] || 'jpg'}`;
        const downloaded = await this.downloadSlackFile(
          downloadUrl,
          groupFolder,
          filename,
        );
        if (!downloaded) return null;

        return processImage(
          downloaded.hostPath,
          attachDir,
          '/workspace/group/attachments',
        );
      }),
    );

    return settled.filter((r): r is ImageAttachment => r !== null);
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
