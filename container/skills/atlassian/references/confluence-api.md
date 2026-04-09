# Confluence Cloud REST API Reference

v2 Base URL: `https://{domain}.atlassian.net/wiki/api/v2`
v1 Base URL: `https://{domain}.atlassian.net/wiki/rest/api`

## v2 API Coverage

| Resource | v2 | v1 Fallback |
|---|---|---|
| Pages CRUD | Yes | - |
| Spaces CRUD | Yes | - |
| Comments CRUD | Yes | - |
| Attachments read/delete | Yes | **Upload requires v1** |
| Labels read | Yes | **Add/Remove requires v1** |
| Content Properties CRUD | Yes | - |
| Search (CQL) | No | **Requires v1** |

## Pages

### List
```
GET /wiki/api/v2/pages?space-id={id}&title={title}&status=current&sort=-modified-date&limit=25
```

### Get
```
GET /wiki/api/v2/pages/{id}?body-format=storage&include-labels=true
```

### Create
```
POST /wiki/api/v2/pages
```
```json
{
  "spaceId": "123",
  "status": "current",
  "title": "Page Title",
  "parentId": "456",
  "body": {
    "representation": "storage",
    "value": "<p>Content in <strong>storage format</strong></p>"
  }
}
```

### Update
```
PUT /wiki/api/v2/pages/{id}
```
```json
{
  "id": "789",
  "status": "current",
  "title": "Updated Title",
  "body": {"representation": "storage", "value": "<p>Updated</p>"},
  "version": {"number": 2, "message": "Updated via API"}
}
```
**Important:** `version.number` must be current version + 1.

### Delete
```
DELETE /wiki/api/v2/pages/{id}?purge=false
```

## Spaces

```
GET /wiki/api/v2/spaces?keys=MYSPACE&type=global&status=current&limit=25
GET /wiki/api/v2/spaces/{id}?description-format=plain&include-icon=true
```

## Comments

Footer and inline comments are separate endpoints.

### Footer Comments
```
GET  /wiki/api/v2/pages/{id}/footer-comments?body-format=storage
POST /wiki/api/v2/footer-comments
Body: {"pageId": "123", "body": {"representation": "storage", "value": "<p>comment</p>"}}

PUT    /wiki/api/v2/footer-comments/{id}
DELETE /wiki/api/v2/footer-comments/{id}
```

### Inline Comments
```
GET  /wiki/api/v2/pages/{id}/inline-comments
POST /wiki/api/v2/inline-comments
Body: {
  "pageId": "123",
  "body": {"representation": "storage", "value": "<p>inline comment</p>"},
  "inlineCommentProperties": {
    "textSelection": "selected text",
    "textSelectionMatchCount": 1,
    "textSelectionMatchIndex": 0
  }
}
```

## Attachments

### List/Get/Delete (v2)
```
GET    /wiki/api/v2/attachments?filename=doc.pdf&mediaType=application/pdf
GET    /wiki/api/v2/attachments/{id}
DELETE /wiki/api/v2/attachments/{id}
```

### Upload (v1 only)
```
POST /wiki/rest/api/content/{pageId}/child/attachment
Headers: X-Atlassian-Token: nocheck, Content-Type: multipart/form-data
Form: file=@/path/to/file.pdf, comment="description", minorEdit=true
```

## Labels

### Read (v2)
```
GET /wiki/api/v2/pages/{id}/labels?prefix=global
```

### Add (v1 only)
```
POST /wiki/rest/api/content/{id}/label
Body: [{"prefix": "global", "name": "my-label"}]
```

### Remove (v1 only)
```
DELETE /wiki/rest/api/content/{id}/label?name=my-label
```

## Content Properties

```
GET    /wiki/api/v2/pages/{id}/properties?key=my-key
POST   /wiki/api/v2/pages/{id}/properties
Body: {"key": "my-key", "value": {"any": "json"}}

GET    /wiki/api/v2/pages/{id}/properties/{propertyId}
PUT    /wiki/api/v2/pages/{id}/properties/{propertyId}
Body: {"key": "my-key", "value": {"updated": true}, "version": {"number": 2}}

DELETE /wiki/api/v2/pages/{id}/properties/{propertyId}
```

## Search (CQL) — v1 Only

```
GET /wiki/rest/api/search?cql={url_encoded_cql}&limit=25&expand=content.body.storage
```

### CQL Quick Reference

**Fields:** `type`, `space`, `space.key`, `title`, `text`, `label`, `ancestor`, `parent`, `creator`, `contributor`, `created`, `lastmodified`, `id`

**Operators:** `=`, `!=`, `~` (contains), `!~`, `>`, `<`, `>=`, `<=`, `IN`, `NOT IN`

**Keywords:** `AND`, `OR`, `NOT`, `ORDER BY asc/desc`

**Functions:** `currentUser()`, `now()`, `startOfDay()`, `endOfDay()`, `startOfWeek()`, `startOfMonth()`, `startOfYear()`

### Common CQL Queries
```
type = page AND space = "MYSPACE" AND title ~ "keyword"
type = page AND label = "important" ORDER BY lastmodified DESC
type = page AND creator = currentUser() AND created > startOfMonth()
type = page AND text ~ "search phrase" AND space IN ("SP1", "SP2")
type = page AND ancestor = 12345
```

**Note:** `expand=content.body.storage` caps `limit` at 50.

## Pagination

### v2: Cursor-based
Request: `cursor` + `limit` (max 250)
Response: `results[]`, `_links.next` (follow for next page)

### v1: Offset-based
Request: `start` + `limit`
Response: `results[]`, `start`, `limit`, `size`, `_links.next`

## Content Body Formats

### Storage Format (HTML-like, recommended)
```json
{"representation": "storage", "value": "<p>Hello <strong>world</strong></p>"}
```
Common tags: `<p>`, `<h1>`-`<h6>`, `<strong>`, `<em>`, `<a href='...'>`, `<ul>/<ol>/<li>`, `<table>/<tr>/<td>`, `<ac:structured-macro>` (macros)

### ADF (JSON-based)
```json
{
  "representation": "atlas_doc_format",
  "value": "{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"Hello\"}]}]}"
}
```
**Critical:** `value` must be a JSON-encoded **string**, not a nested object.
