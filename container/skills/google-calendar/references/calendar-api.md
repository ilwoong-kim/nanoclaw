# Google Calendar API Reference

## Base URL
`https://www.googleapis.com/calendar/v3`

## Event Resource (key fields)

```json
{
  "id": "string",
  "summary": "Event title",
  "description": "Event description",
  "location": "Meeting room or address",
  "start": { "dateTime": "RFC3339", "timeZone": "Asia/Seoul" },
  "end": { "dateTime": "RFC3339", "timeZone": "Asia/Seoul" },
  "attendees": [
    { "email": "user@example.com", "responseStatus": "needsAction|accepted|declined|tentative", "displayName": "Name" }
  ],
  "conferenceData": {
    "entryPoints": [
      { "entryPointType": "video", "uri": "https://meet.google.com/xxx-xxxx-xxx" }
    ],
    "conferenceSolution": { "name": "Google Meet" },
    "createRequest": {
      "requestId": "uuid",
      "conferenceSolutionKey": { "type": "hangoutsMeet" }
    }
  },
  "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO"],
  "reminders": { "useDefault": true },
  "status": "confirmed|tentative|cancelled",
  "htmlLink": "https://www.google.com/calendar/event?eid=..."
}
```

### All-day vs Timed Events
- **All-day**: Use `"start": {"date": "2026-04-10"}, "end": {"date": "2026-04-11"}` (end is exclusive)
- **Timed**: Use `"start": {"dateTime": "2026-04-10T14:00:00+09:00"}`

## ConferenceData (Google Meet)

To create a Meet link, include in the event body:
```json
{
  "conferenceData": {
    "createRequest": {
      "requestId": "<unique-uuid>",
      "conferenceSolutionKey": { "type": "hangoutsMeet" }
    }
  }
}
```
**Important**: Add `?conferenceDataVersion=1` query parameter to the request URL.

The response will include `conferenceData.entryPoints[0].uri` with the Meet link.

## Common Query Parameters

| Parameter | Used In | Description |
|-----------|---------|-------------|
| `timeMin` | events.list | Lower bound (RFC3339) |
| `timeMax` | events.list | Upper bound (RFC3339) |
| `q` | events.list | Free-text search |
| `singleEvents` | events.list | `true` to expand recurring events |
| `orderBy` | events.list | `startTime` (requires singleEvents=true) or `updated` |
| `maxResults` | events.list | Max per page (up to 2500) |
| `pageToken` | events.list | Pagination token |
| `sendUpdates` | insert/update/delete | `all`, `externalOnly`, `none` |
| `conferenceDataVersion` | insert/update | Set to `1` when using conferenceData |

## FreeBusy

**POST** `/freeBusy/query`

Request:
```json
{
  "timeMin": "2026-04-10T09:00:00+09:00",
  "timeMax": "2026-04-10T18:00:00+09:00",
  "items": [
    { "id": "user1@example.com" },
    { "id": "user2@example.com" }
  ]
}
```

Response:
```json
{
  "calendars": {
    "user1@example.com": {
      "busy": [
        { "start": "2026-04-10T10:00:00+09:00", "end": "2026-04-10T11:00:00+09:00" }
      ]
    }
  }
}
```

## CalendarList

**GET** `/users/me/calendarList`

Returns all calendars the user has access to, including meeting room resources.
Meeting rooms typically have `accessRole: "freeBusyReader"` and resource-specific IDs.

## HTTP Methods

| Operation | Method | Endpoint |
|-----------|--------|----------|
| List events | GET | `/calendars/{calendarId}/events` |
| Get event | GET | `/calendars/{calendarId}/events/{eventId}` |
| Create event | POST | `/calendars/{calendarId}/events` |
| Update event | PATCH | `/calendars/{calendarId}/events/{eventId}` |
| Delete event | DELETE | `/calendars/{calendarId}/events/{eventId}` |
| List calendars | GET | `/users/me/calendarList` |
| Free/Busy | POST | `/freeBusy/query` |
