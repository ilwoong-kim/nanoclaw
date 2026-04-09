# Jira Cloud REST API v3 Reference

Base URL: `https://{domain}.atlassian.net/rest/api/3/`
Agile URL: `https://{domain}.atlassian.net/rest/agile/1.0/`

## Issues

### Create
```
POST /rest/api/3/issue
```
```json
{
  "fields": {
    "project": {"key": "PROJ"},
    "issuetype": {"name": "Task"},
    "summary": "Title",
    "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "body"}]}]},
    "assignee": {"accountId": "..."},
    "priority": {"name": "High"},
    "labels": ["backend"],
    "parent": {"key": "PROJ-100"}
  }
}
```
Response 201: `{"id": "10008", "key": "PROJ-2", "self": "..."}`

### Bulk Create
```
POST /rest/api/3/issue/bulk
Body: {"issueUpdates": [{fields, update}, ...]}  (max 50)
```

### Get
```
GET /rest/api/3/issue/{issueIdOrKey}?fields=summary,status&expand=transitions
```

### Edit
```
PUT /rest/api/3/issue/{issueIdOrKey}
```
Set fields: `{"fields": {"summary": "New title"}}`
Update operations: `{"update": {"labels": [{"add": "new"}, {"remove": "old"}]}}`
Response: 204

### Delete
```
DELETE /rest/api/3/issue/{issueIdOrKey}?deleteSubtasks=true
```

### Assign
```
PUT /rest/api/3/issue/{issueIdOrKey}/assignee
Body: {"accountId": "..."} or {"accountId": null}
```

## Search (JQL)

**Important:** Legacy `/rest/api/3/search` is deprecated. Use `/rest/api/3/search/jql`.

```
POST /rest/api/3/search/jql
```
```json
{
  "jql": "project = PROJ AND status = 'In Progress'",
  "maxResults": 50,
  "fields": ["summary", "status", "assignee"]
}
```
Pagination: use `nextPageToken` (no `total` available).

### Common JQL
```
project = ARK AND status = "In Progress"
project = ARK AND assignee = currentUser()
project = ARK AND sprint in openSprints()
project = ARK AND labels = "backend" ORDER BY priority DESC
project = ARK AND created >= -7d
project = ARK AND parent = ARK-307
issuetype = "Sub-task" AND parent = ARK-489
```

## Transitions

```
GET  /rest/api/3/issue/{key}/transitions
POST /rest/api/3/issue/{key}/transitions
Body: {"transition": {"id": "31"}}
```

## Comments

```
GET  /rest/api/3/issue/{key}/comment
POST /rest/api/3/issue/{key}/comment
Body: {"body": {ADF document}}

PUT    /rest/api/3/issue/{key}/comment/{commentId}
DELETE /rest/api/3/issue/{key}/comment/{commentId}
```

## Attachments

```
POST /rest/api/3/issue/{key}/attachments
Headers: X-Atlassian-Token: no-check, Content-Type: multipart/form-data
Form field: file

GET    /rest/api/3/attachment/{id}
DELETE /rest/api/3/attachment/{id}
```

## Projects
```
GET /rest/api/3/project/search?maxResults=50&query=name
GET /rest/api/3/project/{projectIdOrKey}
```

## Users
```
GET /rest/api/3/myself
GET /rest/api/3/user?accountId={id}
GET /rest/api/3/user/search?query={name_or_email}
GET /rest/api/3/user/assignable/search?project={key}
```

## Labels / Priorities / Statuses
```
GET /rest/api/3/label
GET /rest/api/3/priority/search
GET /rest/api/3/statuses/search
GET /rest/api/3/statuscategory
```

## Worklogs
```
GET  /rest/api/3/issue/{key}/worklog
POST /rest/api/3/issue/{key}/worklog
Body: {"timeSpentSeconds": 3600, "started": "2024-01-15T10:00:00.000+0000"}

PUT    /rest/api/3/issue/{key}/worklog/{id}
DELETE /rest/api/3/issue/{key}/worklog/{id}
```

## Agile (Boards & Sprints)

### Boards
```
GET /rest/agile/1.0/board?type=scrum&name=...
GET /rest/agile/1.0/board/{boardId}
GET /rest/agile/1.0/board/{boardId}/sprint
GET /rest/agile/1.0/board/{boardId}/issue
GET /rest/agile/1.0/board/{boardId}/backlog
GET /rest/agile/1.0/board/{boardId}/epic
```

### Sprints
```
POST /rest/agile/1.0/sprint
Body: {"name": "Sprint 1", "originBoardId": 1, "startDate": "...", "endDate": "...", "goal": "..."}

GET    /rest/agile/1.0/sprint/{sprintId}
PUT    /rest/agile/1.0/sprint/{sprintId}
DELETE /rest/agile/1.0/sprint/{sprintId}

GET  /rest/agile/1.0/sprint/{sprintId}/issue
POST /rest/agile/1.0/sprint/{sprintId}/issue
Body: {"issues": ["PROJ-1", "PROJ-2"]}
```
Sprint states: `future`, `active`, `closed`

### Epics
```
GET  /rest/agile/1.0/epic/{epicIdOrKey}
GET  /rest/agile/1.0/epic/{epicIdOrKey}/issue
POST /rest/agile/1.0/epic/{epicIdOrKey}/issue
```

## Pagination

Standard (most endpoints): `startAt` + `maxResults` → `total`, `isLast`, `values[]`
JQL search: `nextPageToken` → `issues[]` (no `total`)

## Rate Limiting

HTTP 429 returned. Check headers: `Retry-After`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
Use exponential backoff with jitter.

## ADF (Atlassian Document Format)

v3 requires ADF for description, comment body, worklog comment:
```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
    {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Title"}]},
    {"type": "bulletList", "content": [
      {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "item"}]}]}
    ]},
    {"type": "codeBlock", "attrs": {"language": "python"}, "content": [{"type": "text", "text": "code"}]}
  ]
}
```
