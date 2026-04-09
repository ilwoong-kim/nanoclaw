---
name: atlassian
description: >
  Atlassian Cloud REST API integration for Jira and Confluence.
  Use when tasks involve: (1) Jira — creating/editing/searching issues, JQL queries,
  transitions, comments, attachments, sprints, boards, worklogs;
  (2) Confluence — creating/editing/searching pages, CQL queries, comments, labels,
  attachments, spaces; (3) Any mention of Jira issue keys (e.g., ARK-XXX),
  Confluence page operations, or Atlassian-related queries.
  Triggers: "create jira issue", "search jira", "jql", "confluence page",
  "cql search", "jira transition", "update confluence", "atlassian", "jira comment",
  "sprint", "board", "worklog", "confluence label".
---

# Atlassian Cloud REST API

## When to Use This Skill

**Always use this skill's Python script instead of browsing the web** for Atlassian. Web browsing will fail due to login requirements.

### Explicit triggers
User mentions Jira, Confluence, 이슈, 티켓, 페이지, 스프린트, 보드, ARK-*, quantit.atlassian.net


## Credentials

Credentials are injected via environment variables by the host:
- `ATLASSIAN_DOMAIN` — Atlassian domain (e.g., `quantit` for quantit.atlassian.net)
- `ATLASSIAN_EMAIL` — Account email
- `ATLASSIAN_API_TOKEN` — API token

The Python script reads these automatically. No setup needed inside the container.

## Default User

| Field | Value |
|-------|-------|
| Name | 김일웅 (ilwoong.kim) |
| Email | ilwoong.kim@quantit.io |
| Account ID | `6040590ac58c72007140a156` |

When creating/assigning issues, use this account ID as the default assignee unless specified otherwise.

## Default Workspaces

Unless the user specifies a different space or URL, use these defaults:

### Confluence Spaces

| Space | Key | Purpose |
|-------|-----|---------|
| QuantIt Wiki | `QW` | 회사 전반 — 문화, 복지, 소개, 정책 등 |
| Arkraft | `ARK` | Arkraft 프로젝트 문서 |
| ilwoong 개인 | `~900350278` | 사용자 개인 페이지 |

Search examples with default spaces:
```bash
# 회사 관련 질문 → QW 스페이스 검색
python3 $SCRIPT confluence search 'type = page AND space = "QW" AND title ~ "keyword"'

# Arkraft 프로젝트 문서 → ARK 스페이스 검색
python3 $SCRIPT confluence search 'type = page AND space = "ARK" AND title ~ "keyword"'

# 개인 페이지 → ~900350278 스페이스 검색
python3 $SCRIPT confluence search 'type = page AND space = "~900350278" AND title ~ "keyword"'
```

### Jira Project

| Project | Key | Board |
|---------|-----|-------|
| Arkraft | `ARK` | Board 492 |

Default JQL queries:
```bash
# 내 진행중 이슈
python3 $SCRIPT jira search 'project = ARK AND assignee = currentUser() AND status != Done'

# 현재 스프린트
python3 $SCRIPT jira search 'project = ARK AND sprint in openSprints()'
```

## Quick Reference

### Script Location

```bash
SCRIPT="/home/node/.claude/skills/atlassian/scripts/atlassian_api.py"
```

### Jira via CLI Script

```bash
# Auth check
python3 $SCRIPT jira myself

# Issues
python3 $SCRIPT jira get-issue ARK-307
python3 $SCRIPT jira create-issue --project ARK --type Task --summary "Title" --parent ARK-307
python3 $SCRIPT jira edit-issue ARK-100 --summary "New title" --add-labels backend
# NOTE: edit-issue only supports --summary, --add-labels, --remove-labels
# For description and other fields, use Direct API (see below)
python3 $SCRIPT jira delete-issue ARK-100 --delete-subtasks

# Search (JQL)
python3 $SCRIPT jira search 'project = ARK AND status = "In Progress"'
python3 $SCRIPT jira search 'assignee = currentUser() AND sprint in openSprints()'

# Transitions & Comments
python3 $SCRIPT jira transitions ARK-100
python3 $SCRIPT jira transition ARK-100 "Done"
python3 $SCRIPT jira add-comment ARK-100 "comment text"

# Users
python3 $SCRIPT jira search-users "홍길동"
```

### Confluence via CLI Script

```bash
# Spaces
python3 $SCRIPT confluence list-spaces
python3 $SCRIPT confluence get-space 12345

# Pages
python3 $SCRIPT confluence get-page 12345 --body-format storage
python3 $SCRIPT confluence list-pages --space-id 12345 --title "Page Title"
python3 $SCRIPT confluence create-page --space-id 12345 --title "New Page" --body "<p>content</p>"
python3 $SCRIPT confluence update-page 12345 --title "Updated" --body "<p>new</p>" --version 2
python3 $SCRIPT confluence delete-page 12345

# Search (CQL)
python3 $SCRIPT confluence search 'type = page AND space = "MYSPACE" AND title ~ "keyword"'

# Labels & Comments
python3 $SCRIPT confluence add-labels 12345 my-label another-label
python3 $SCRIPT confluence remove-label 12345 old-label
python3 $SCRIPT confluence add-comment 12345 "<p>comment</p>"
```

### Direct API Calls (Python)

For operations not covered by the CLI (e.g., updating description, custom fields):

```python
import sys
sys.path.insert(0, "/home/node/.claude/skills/atlassian/scripts")
from atlassian_api import load_credentials, validate_credentials, api_request

creds = load_credentials()
validate_credentials(creds)

# Any custom endpoint
result = api_request(creds, "GET", "/rest/api/3/issue/ARK-307")
result = api_request(creds, "POST", "/rest/api/3/issue", body={...})

# Update description (ADF format) — CLI edit-issue does NOT support this
result = api_request(creds, "PUT", "/rest/api/3/issue/ARK-100", body={
    "fields": {
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Section Title"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Body text here."}]},
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item 1"}]}]},
                ]},
            ]
        }
    }
})
```

## API Reference (Progressive Disclosure)

Detailed endpoint references — load only when needed:

- **Jira API**: See [references/jira-api.md](references/jira-api.md) — Issue CRUD, JQL, transitions, comments, attachments, worklogs, boards, sprints, epics, ADF format
- **Confluence API**: See [references/confluence-api.md](references/confluence-api.md) — Page CRUD, spaces, CQL search, comments, labels, attachments, storage format, v2/v1 endpoint coverage

## Key Conventions

### Jira
- API v3 uses **ADF** (Atlassian Document Format) for rich text fields (description, comments)
- The `text_to_adf()` helper converts plain text to ADF automatically
- JQL search uses `/rest/api/3/search/jql` (legacy `/search` is deprecated)
- Pagination via `nextPageToken` (no `total` count available)

### Confluence
- Prefer **v2 API** (`/wiki/api/v2/`) for CRUD operations
- Use **v1 API** (`/wiki/rest/api/`) for: CQL search, label writes, attachment uploads
- Page updates require incrementing `version.number` by 1
- Body format: `storage` (HTML-like) is simpler; `atlas_doc_format` (ADF) requires JSON-stringified value

### Authentication
- Basic Auth: `base64(email:api_token)` in `Authorization` header
- Rate limits: exponential backoff on HTTP 429
