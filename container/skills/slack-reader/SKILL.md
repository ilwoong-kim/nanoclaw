---
name: slack
description: >
  Slack workspace access via Web API. Read operations use User Token,
  write operations use Bot Token (Luffy-Bot identity) — enforced at the code level.
  Use when: (1) reading Slack channel history or threads, (2) searching messages,
  (3) checking mentions/DMs, (4) listing channels/users, (5) adding reactions,
  (6) pinning messages, (7) managing bookmarks, (8) any Slack API operation.
  Triggers: "slack", "슬랙", "channel", "채널", "thread", "스레드", "DM",
  "멘션", "mention", "unread", "읽어", "slack search", "slack history",
  "reaction", "리액션", "pin", "핀".
---

# Slack

Read and write access to the Slack workspace.

## Token Enforcement (Code-Level)

Token selection is **automatic and enforced in code** — you cannot choose which token to use:

- **Read methods** → User Token (personal scope, `xoxp-`)
- **Write methods** → Bot Token (Luffy-Bot identity, `xoxb-`)

This prevents accidentally performing write operations as the owner's personal account.

**IMPORTANT**: Always use `slack.py` for Slack API calls. Never use `curl`, `urllib`, or direct HTTP requests with raw tokens (`$SLACK_USER_TOKEN`, `$SLACK_BOT_TOKEN`).

## Credentials

`SLACK_USER_TOKEN` and `SLACK_BOT_TOKEN` are injected via environment variables by the host. No setup needed inside the container.

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

### Generic API Caller (read methods)

```bash
python3 $SLACK/slack.py <method> [key=value ...] [--paginate <response_key>]
```

Read methods:
- `conversations.info`, `conversations.list`, `conversations.history`, `conversations.replies`
- `conversations.members`
- `users.info`, `users.list`, `users.lookupByEmail`
- `reactions.get`, `reactions.list`
- `pins.list`
- `bookmarks.list`
- `search.messages`, `search.files`
- `auth.test`
- `team.info`
- `usergroups.list`, `usergroups.users.list`
- `files.list`, `files.info`

## Write Operations

All write operations are performed as **Luffy-Bot** (Bot Token).

### Sending Messages

For **conversation replies** (responding to the user), use the `send_message` tool — it handles message splitting, thread routing, and heartbeat management through the host.

For **standalone messages** (notifications, posting to other channels):

```bash
python3 $SLACK/slack.py chat.postMessage channel=C12345 text="Hello!"
python3 $SLACK/slack.py chat.postEphemeral channel=C12345 user=U12345 text="Only you can see this"
```

### Reactions

```bash
python3 $SLACK/slack.py reactions.add channel=C12345 name=thumbsup timestamp=1234567890.123456
python3 $SLACK/slack.py reactions.remove channel=C12345 name=thumbsup timestamp=1234567890.123456
```

### Pins

```bash
python3 $SLACK/slack.py pins.add channel=C12345 timestamp=1234567890.123456
python3 $SLACK/slack.py pins.remove channel=C12345 timestamp=1234567890.123456
```

### Bookmarks

```bash
python3 $SLACK/slack.py bookmarks.add channel_id=C12345 title="My Bookmark" type=link link="https://example.com"
python3 $SLACK/slack.py bookmarks.edit channel_id=C12345 bookmark_id=Bk12345 title="Updated"
python3 $SLACK/slack.py bookmarks.remove channel_id=C12345 bookmark_id=Bk12345
```

### Channel Management

```bash
python3 $SLACK/slack.py conversations.setPurpose channel=C12345 purpose="New purpose"
python3 $SLACK/slack.py conversations.setTopic channel=C12345 topic="New topic"
python3 $SLACK/slack.py conversations.invite channel=C12345 users=U12345
python3 $SLACK/slack.py conversations.archive channel=C12345
```

### Reminders

```bash
python3 $SLACK/slack.py reminders.add text="Check deployment" time=1234567890
python3 $SLACK/slack.py reminders.complete reminder=Rm12345
python3 $SLACK/slack.py reminders.delete reminder=Rm12345
```

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

### 메시지에 리액션 달기
```bash
python3 $SLACK/slack.py reactions.add channel=C12345 name=white_check_mark timestamp=1234567890.123456
```

## Workspace Directory

For known channel IDs, DM channel IDs, and team member info, see [references/workspace.md](references/workspace.md).

## API Reference

For the full list of supported methods and parameters, see [references/api_methods.md](references/api_methods.md).
