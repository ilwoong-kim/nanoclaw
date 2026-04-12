---
name: slack-reader
description: >
  Read-only Slack workspace access via Web API with user token.
  Read channel history, threads, DMs, search messages, list channels/users.
  Use when: (1) reading Slack channel history or threads, (2) searching messages,
  (3) checking mentions/DMs, (4) listing channels/users, (5) any read-only Slack operation.
  Triggers: "slack", "슬랙", "channel", "채널", "thread", "스레드", "DM",
  "멘션", "mention", "unread", "읽어", "slack search", "slack history".
---

# Slack Reader (Read-Only)

Read-only access to the Slack workspace. Write methods are blocked at the code level and will fail with an error.

When you need to send a message to a Slack channel:
- **Always use the `send_message` tool** — this sends messages as Luffy-Bot (Bot identity)
- **Never use `slack.py chat.postMessage`** — this is blocked and would incorrectly send as the owner's personal account

## Credentials

`SLACK_USER_TOKEN` is injected via environment variable by the host. No setup needed inside the container.

## Script Location

```bash
SLACK="/home/node/.claude/skills/slack-reader/scripts"
```

## Read Operations

### Read Channel/DM History

```bash
python3 $SLACK/read_history.py <channel_id> [--threads] [--limit N] [--oldest TS] [--latest TS] [--json]
```

- `--threads`: Expand all thread replies inline
- `--json`: Output raw JSON instead of formatted text
- Default limit: 50 messages

### List Channels/DMs

```bash
python3 $SLACK/list_conversations.py [--types public_channel,private_channel,mpim,im] [--json]
```

### Search Messages

```bash
python3 $SLACK/search_messages.py "<query>" [--sort score|timestamp] [--count N] [--json]
```

Query modifiers: `in:#channel`, `from:@user`, `has:link`, `before:YYYY-MM-DD`, `after:YYYY-MM-DD`

### Generic API Caller (read-only methods only)

```bash
python3 $SLACK/slack.py <method> [key=value ...] [--paginate <response_key>]
```

Allowed read-only methods:
- `conversations.info`, `conversations.list`, `conversations.history`, `conversations.replies`
- `conversations.members`
- `users.info`, `users.list`, `users.lookupByEmail`
- `reactions.get`
- `pins.list`
- `bookmarks.list`
- `search.messages`, `search.files`
- `auth.test`
- `team.info`
- `usergroups.list`, `usergroups.users.list`
- `files.list`, `files.info`

**Do NOT call write methods** (chat.postMessage, chat.update, chat.delete, reactions.add, pins.add, files.upload, etc.)

## Common Workflows

### 나한테 멘션 온 것 확인
```bash
python3 $SLACK/search_messages.py "to:me" --sort timestamp --count 20
```

### 특정 채널 최근 대화 읽기
```bash
python3 $SLACK/read_history.py <channel_id> --threads --limit 30
```

### 특정 채널에서 키워드 검색
```bash
python3 $SLACK/search_messages.py "in:#channel-name keyword" --count 10
```

### DM 확인
```bash
# 1. DM 목록
python3 $SLACK/list_conversations.py --types im

# 2. DM 읽기
python3 $SLACK/read_history.py <dm_channel_id> --threads
```

### 특정 사용자가 보낸 메시지 찾기
```bash
python3 $SLACK/search_messages.py "from:@username" --sort timestamp --count 20
```

## Workspace Directory

For known channel IDs, DM channel IDs, and team member info, see [references/workspace.md](references/workspace.md).

## API Reference

For the full list of supported methods and parameters, see [references/api_methods.md](references/api_methods.md).
