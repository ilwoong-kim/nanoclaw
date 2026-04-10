---
name: google-calendar
description: >
  Google Calendar API integration for events, scheduling, and availability.
  Use when tasks involve: (1) creating/listing/updating/deleting calendar events;
  (2) scheduling meetings with attendees and Google Meet links;
  (3) checking availability (free/busy); (4) finding meeting rooms;
  (5) listing calendars.
  Triggers: "calendar", "캘린더", "일정", "meeting", "회의", "미팅",
  "schedule", "스케줄", "google meet", "free busy", "availability",
  "회의실", "meeting room", "참석자", "attendee".
---

# Google Calendar API

## When to Use This Skill

**Always use this skill's Python script for Google Calendar operations.** Web browsing will fail due to login requirements.

### Explicit triggers
User mentions 캘린더, 일정, 회의, 미팅, 스케줄, 구글밋, 회의실, 참석자, calendar, meeting, schedule, Google Meet, attendee, free/busy

## Credentials

OAuth credentials are mounted read-only from the host at `/home/node/.calendar-mcp/`. The script refreshes the access token automatically on every invocation. No setup needed inside the container.

## Script Location

```bash
SCRIPT="/home/node/.claude/skills/google-calendar/scripts/google_calendar_api.py"
```

## Quick Reference

### Auth Check
```bash
python3 $SCRIPT auth
```

### List Events
```bash
# Today's events
python3 $SCRIPT event list --from 2026-04-10T00:00:00+09:00 --to 2026-04-11T00:00:00+09:00

# Search events
python3 $SCRIPT event list --from 2026-04-10 --to 2026-04-17 --q "meeting"

# Specific calendar
python3 $SCRIPT event list --from 2026-04-10 --to 2026-04-11 --calendar CALENDAR_ID
```

### Get Event
```bash
python3 $SCRIPT event get EVENT_ID
```

### Create Event
```bash
# Simple event
python3 $SCRIPT event create \
  --summary "Team Sync" \
  --start "2026-04-11T14:00:00+09:00" \
  --end "2026-04-11T15:00:00+09:00"

# Full-featured: attendees + Google Meet + location
python3 $SCRIPT event create \
  --summary "Sprint Planning" \
  --start "2026-04-11T10:00:00+09:00" \
  --end "2026-04-11T11:00:00+09:00" \
  --attendees "user1@example.com,user2@example.com" \
  --meet \
  --location "회의실 A" \
  --description "Sprint 42 planning session"

# All-day event
python3 $SCRIPT event create \
  --summary "Company Holiday" \
  --start "2026-04-15" \
  --end "2026-04-16"

# Suppress email notifications
python3 $SCRIPT event create --summary "..." --start "..." --end "..." --send-updates none
```

### Update Event
```bash
# Change title
python3 $SCRIPT event update EVENT_ID --summary "New Title"

# Add attendees to existing event (merges with current attendees)
python3 $SCRIPT event update EVENT_ID --add-attendees "user3@example.com,user4@example.com"

# Add Google Meet to existing event (skips if already present)
python3 $SCRIPT event update EVENT_ID --meet

# Replace all attendees
python3 $SCRIPT event update EVENT_ID --attendees "only-this@example.com"

# Reschedule
python3 $SCRIPT event update EVENT_ID \
  --start "2026-04-12T14:00:00+09:00" \
  --end "2026-04-12T15:00:00+09:00"
```

### Delete Event
```bash
python3 $SCRIPT event delete EVENT_ID
python3 $SCRIPT event delete EVENT_ID --send-updates none
```

### List Calendars
```bash
# Lists all calendars including meeting room resources
python3 $SCRIPT calendar list
```

### Check Free/Busy
```bash
python3 $SCRIPT freebusy check \
  --emails "user1@example.com,user2@example.com" \
  --start "2026-04-11T09:00:00+09:00" \
  --end "2026-04-11T18:00:00+09:00"
```

## Direct API Calls (Python)

```python
import sys
sys.path.insert(0, "/home/node/.claude/skills/google-calendar/scripts")
from google_calendar_api import load_and_refresh_token, api_request

token = load_and_refresh_token()

# Example: get a specific event
event = api_request(token, "GET", "/calendars/primary/events/EVENT_ID")
```

## Key Conventions

- **Datetime format**: RFC3339 with timezone offset (e.g., `2026-04-10T14:00:00+09:00`). For all-day events use `YYYY-MM-DD`.
- **Default calendar**: `primary` (user's main calendar). Use `--calendar CALENDAR_ID` for other calendars.
- **Attendees**: Always comma-separated emails. Use `--add-attendees` to merge with existing; `--attendees` to replace.
- **Google Meet**: Use `--meet` flag. On create, always adds. On update, only adds if not already present.
- **Send updates**: Controls email notifications to attendees. Default is `all`. Use `none` for silent changes.
- **Meeting rooms**: Appear in `calendar list` output. Use their calendar ID as an attendee email to book them.
