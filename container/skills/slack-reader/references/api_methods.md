# Slack Web API Methods Reference

All methods use POST with JSON body. Auth via `Authorization: Bearer xoxp-...` header.
Base URL: `https://slack.com/api/`

Use `scripts/slack.py` for any method below:
```bash
python scripts/slack.py <method> [key=value ...] [--paginate <key>]
```

## Conversations (Channels / DMs / Group DMs)

| Method | Description | Paginate Key |
|--------|-------------|-------------|
| `conversations.list` | List channels/DMs user belongs to | `channels` |
| `conversations.history` | Get messages in a conversation | `messages` |
| `conversations.replies` | Get thread replies | `messages` |
| `conversations.info` | Get conversation metadata | - |
| `conversations.members` | List members of a conversation | `members` |
| `conversations.open` | Open/resume a DM or multi-party DM | - |
| `conversations.close` | Close a DM or multi-party DM | - |
| `conversations.create` | Create a channel | - |
| `conversations.join` | Join a channel | - |
| `conversations.leave` | Leave a channel | - |
| `conversations.invite` | Invite users to a channel | - |
| `conversations.kick` | Remove a user from a channel | - |
| `conversations.archive` | Archive a channel | - |
| `conversations.unarchive` | Unarchive a channel | - |
| `conversations.rename` | Rename a channel | - |
| `conversations.setPurpose` | Set conversation purpose | - |
| `conversations.setTopic` | Set conversation topic | - |
| `conversations.mark` | Set cursor (read position) in a conversation | - |

### Key Parameters

**conversations.list**
- `types`: Comma-separated: `public_channel`, `private_channel`, `mpim`, `im`
- `exclude_archived`: `true`/`false`
- `limit`: 1-1000 (default 100)

**conversations.history / conversations.replies**
- `channel`: Channel ID (required)
- `ts`: Thread parent timestamp (required for replies)
- `oldest` / `latest`: Unix timestamps for time range
- `inclusive`: Include messages with oldest/latest ts
- `limit`: 1-1000 (default 100)

**conversations.open** (DM)
- `users`: Comma-separated user IDs (up to 8 for MPIM)
- `return_im`: Return full IM object

## Messages

| Method | Description |
|--------|-------------|
| `chat.postMessage` | Send a message |
| `chat.update` | Update a message |
| `chat.delete` | Delete a message |
| `chat.meMessage` | Send a /me message |
| `chat.postEphemeral` | Send an ephemeral message (visible only to one user) |
| `chat.scheduleMessage` | Schedule a message |
| `chat.scheduledMessages.list` | List scheduled messages |
| `chat.deleteScheduledMessage` | Delete a scheduled message |
| `chat.getPermalink` | Get permalink for a message |
| `chat.unfurl` | Provide custom unfurl for URLs |

### Key Parameters

**chat.postMessage**
- `channel`: Channel ID (required)
- `text`: Message text with mrkdwn (required, or provide `blocks`)
- `blocks`: Block Kit blocks (JSON array)
- `thread_ts`: Parent message ts (for thread reply)
- `reply_broadcast`: `true` to also post to channel when replying to thread
- `unfurl_links` / `unfurl_media`: Control link/media previews
- `mrkdwn`: `true`/`false`

**chat.update**
- `channel`: Channel ID (required)
- `ts`: Message timestamp (required)
- `text` / `blocks`: New content

## Users

| Method | Description | Paginate Key |
|--------|-------------|-------------|
| `users.list` | List all users | `members` |
| `users.info` | Get single user info | - |
| `users.profile.get` | Get user profile | - |
| `users.profile.set` | Set own profile fields | - |
| `users.getPresence` | Get user presence | - |
| `users.setPresence` | Set own presence | - |
| `users.identity` | Get user identity (OAuth) | - |
| `users.lookupByEmail` | Find user by email | - |
| `users.conversations` | List conversations for a user | `channels` |

## Reactions

| Method | Description |
|--------|-------------|
| `reactions.add` | Add a reaction |
| `reactions.remove` | Remove a reaction |
| `reactions.get` | Get reactions for an item |
| `reactions.list` | List reactions by a user |

### Key Parameters
- `channel`: Channel ID
- `timestamp`: Message timestamp
- `name`: Emoji name without colons (e.g., `thumbsup`)

## Files

| Method | Description | Paginate Key |
|--------|-------------|-------------|
| `files.list` | List files | `files` |
| `files.info` | Get file info | - |
| `files.upload` | Upload a file (use `multipart/form-data`) | - |
| `files.delete` | Delete a file | - |
| `files.sharedPublicURL` | Create public URL for a file | - |
| `files.revokePublicURL` | Revoke public URL | - |

**Note**: `files.upload` requires `multipart/form-data`, not JSON. Use curl or a custom script.

## Pins

| Method | Description |
|--------|-------------|
| `pins.add` | Pin a message |
| `pins.remove` | Unpin a message |
| `pins.list` | List pinned items in a channel |

## Bookmarks

| Method | Description |
|--------|-------------|
| `bookmarks.add` | Add a bookmark to a channel |
| `bookmarks.edit` | Edit a bookmark |
| `bookmarks.list` | List bookmarks for a channel |
| `bookmarks.remove` | Remove a bookmark |

## Stars (Saved Items)

| Method | Description |
|--------|-------------|
| `stars.add` | Star an item |
| `stars.remove` | Remove a star |
| `stars.list` | List starred items |

## Search

| Method | Description |
|--------|-------------|
| `search.messages` | Search messages |
| `search.files` | Search files |
| `search.all` | Search messages and files |

### Key Parameters
- `query`: Search string (supports `in:`, `from:`, `has:`, `before:`, `after:`, `during:`)
- `sort`: `score` or `timestamp`
- `sort_dir`: `asc` or `desc`
- `count`: Results per page (max 100)
- `page`: Page number

## Reminders

| Method | Description |
|--------|-------------|
| `reminders.add` | Create a reminder |
| `reminders.complete` | Mark reminder complete |
| `reminders.delete` | Delete a reminder |
| `reminders.info` | Get reminder info |
| `reminders.list` | List reminders |

## Emoji

| Method | Description |
|--------|-------------|
| `emoji.list` | List custom emoji |

## Team / Workspace Info

| Method | Description |
|--------|-------------|
| `team.info` | Get workspace info |
| `team.profile.get` | Get workspace profile field definitions |
| `team.accessLogs` | Get workspace access logs |
| `team.billableInfo` | Get billable info |

## User Groups

| Method | Description | Paginate Key |
|--------|-------------|-------------|
| `usergroups.list` | List user groups | - |
| `usergroups.create` | Create a user group | - |
| `usergroups.update` | Update a user group | - |
| `usergroups.disable` | Disable a user group | - |
| `usergroups.enable` | Enable a user group | - |
| `usergroups.users.list` | List users in a group | - |
| `usergroups.users.update` | Update group members | - |

## Views (Modals / Home Tab)

| Method | Description |
|--------|-------------|
| `views.open` | Open a modal |
| `views.push` | Push a new view onto a modal stack |
| `views.update` | Update a view |
| `views.publish` | Publish a Home tab view |

## Admin (requires admin scopes)

| Method | Description |
|--------|-------------|
| `admin.conversations.invite` | Invite to channel (admin) |
| `admin.conversations.archive` | Archive channel (admin) |
| `admin.users.list` | List workspace users (admin) |
| `admin.users.invite` | Invite user to workspace |
| `admin.users.remove` | Remove user from workspace |
| `admin.users.assign` | Assign user to workspace |

## mrkdwn Formatting (for message text)

```
*bold*  _italic_  ~strikethrough~  `code`  ```code block```
<https://example.com|link text>
<@U12345>          mention user
<#C12345>          mention channel
<!here>  <!channel>  <!everyone>   special mentions
:emoji_name:       emoji
> blockquote
• bullet (use actual bullet character)
```

## Block Kit Quick Reference

Common block types for `blocks` parameter:

```json
[
  {"type": "section", "text": {"type": "mrkdwn", "text": "*Bold title*\nDescription"}},
  {"type": "divider"},
  {"type": "section", "text": {"type": "mrkdwn", "text": "With button"}, "accessory": {"type": "button", "text": {"type": "plain_text", "text": "Click"}, "action_id": "btn", "url": "https://example.com"}},
  {"type": "context", "elements": [{"type": "mrkdwn", "text": "Footer text"}]},
  {"type": "header", "text": {"type": "plain_text", "text": "Header"}},
  {"type": "image", "image_url": "https://...", "alt_text": "desc"}
]
```
