#!/usr/bin/env python3
"""Google Calendar API helper for NanoClaw container agents.

Usage:
    # Auth check
    python google_calendar_api.py auth

    # Events
    python google_calendar_api.py event list --from 2026-04-10T00:00:00+09:00 --to 2026-04-11T00:00:00+09:00
    python google_calendar_api.py event list --from 2026-04-10 --to 2026-04-11 --q "meeting"
    python google_calendar_api.py event get EVENT_ID
    python google_calendar_api.py event create --summary "Meeting" --start "2026-04-10T14:00:00+09:00" --end "2026-04-10T15:00:00+09:00"
    python google_calendar_api.py event create --summary "Meeting" --start "..." --end "..." --attendees "a@x.com,b@x.com" --meet
    python google_calendar_api.py event update EVENT_ID --summary "New title"
    python google_calendar_api.py event update EVENT_ID --add-attendees "c@x.com" --meet
    python google_calendar_api.py event delete EVENT_ID

    # Calendars
    python google_calendar_api.py calendar list

    # Free/Busy
    python google_calendar_api.py freebusy check --emails "a@x.com,b@x.com" --start "..." --end "..."

Credentials:
    Reads OAuth files from /home/node/.calendar-mcp/ (mounted read-only):
      - gcp-oauth.keys.json  (client_id, client_secret, token_uri)
      - credentials.json     (refresh_token)
    Token is refreshed in-memory on every invocation.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_BASE = "https://www.googleapis.com/calendar/v3"
TOKEN_URI = "https://oauth2.googleapis.com/token"

# Container mount path; override with env var for local testing
CRED_DIR = os.environ.get("GOOGLE_CALENDAR_CRED_DIR", "/home/node/.calendar-mcp")


# -- Credentials & Token Refresh -----------------------------------------------

def load_and_refresh_token() -> str:
    """Load OAuth credentials from mounted files and refresh the access token."""
    oauth_path = os.path.join(CRED_DIR, "gcp-oauth.keys.json")
    creds_path = os.path.join(CRED_DIR, "credentials.json")

    try:
        with open(oauth_path) as f:
            oauth = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Cannot load {oauth_path}: {exc}", file=sys.stderr)
        print("Ensure Google Calendar OAuth is set up on the host (~/.calendar-mcp/).", file=sys.stderr)
        sys.exit(1)

    # Support both top-level and nested (web/installed) key formats
    if "web" in oauth:
        oauth = oauth["web"]
    elif "installed" in oauth:
        oauth = oauth["installed"]

    try:
        with open(creds_path) as f:
            creds = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Cannot load {creds_path}: {exc}", file=sys.stderr)
        print("Ensure Google Calendar OAuth is set up on the host (~/.calendar-mcp/).", file=sys.stderr)
        sys.exit(1)

    client_id = oauth.get("client_id", "")
    client_secret = oauth.get("client_secret", "")
    refresh_token = creds.get("refresh_token", "")
    token_uri = oauth.get("token_uri", TOKEN_URI)

    if not all([client_id, client_secret, refresh_token]):
        print("Incomplete OAuth credentials (need client_id, client_secret, refresh_token).", file=sys.stderr)
        sys.exit(1)

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(token_uri, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode())
            access_token = token_data.get("access_token", "")
            if not access_token:
                print("Token refresh succeeded but no access_token in response.", file=sys.stderr)
                sys.exit(1)
            return access_token
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.readable() else ""
        print(f"Token refresh failed — HTTP {e.code}: {e.reason}", file=sys.stderr)
        print(error_body, file=sys.stderr)
        print("\nThe refresh token may be expired or revoked.", file=sys.stderr)
        print("Re-authenticate on the host: delete ~/.calendar-mcp/credentials.json and re-run setup.", file=sys.stderr)
        sys.exit(1)


# -- HTTP ----------------------------------------------------------------------

def api_request(
    token: str,
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
) -> dict | list | str:
    """Make an authenticated request to the Google Calendar API."""
    url = f"{API_BASE}{path}" if path.startswith("/") else path

    if params:
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "nanoclaw-google-calendar-skill",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode()
            if not resp_body:
                return {"status": resp.status, "message": "Success (no content)"}
            return json.loads(resp_body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.readable() else ""
        try:
            error_json = json.loads(error_body)
        except json.JSONDecodeError:
            error_json = {"raw": error_body}
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        print(json.dumps(error_json, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


def paginate(
    token: str,
    path: str,
    params: dict | None = None,
    max_items: int = 250,
    items_key: str = "items",
) -> list:
    """Paginate through Google Calendar API results using nextPageToken."""
    params = dict(params or {})
    params["maxResults"] = min(max_items, 250)
    all_items: list = []

    while len(all_items) < max_items:
        result = api_request(token, "GET", path, params=params)
        if not isinstance(result, dict):
            break
        items = result.get(items_key, [])
        all_items.extend(items)
        next_token = result.get("nextPageToken")
        if not next_token:
            break
        params["pageToken"] = next_token

    return all_items[:max_items]


# -- Helpers -------------------------------------------------------------------

def parse_datetime(value: str) -> dict:
    """Convert a datetime string to Google Calendar start/end format.

    Returns {"date": "YYYY-MM-DD"} for all-day events or
    {"dateTime": "...", "timeZone": "..."} for timed events.
    """
    # All-day: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return {"date": value}

    # Timed event — pass through as-is (must be RFC3339)
    tz = os.environ.get("TZ", "Asia/Seoul")
    result = {"dateTime": value}
    # Only add timeZone if the value doesn't already have offset info
    if not re.search(r"[+-]\d{2}:\d{2}$", value) and not value.endswith("Z"):
        result["timeZone"] = tz
    return result


def parse_emails(value: str) -> list[dict]:
    """Convert comma-separated emails to attendee objects."""
    return [{"email": e.strip()} for e in value.split(",") if e.strip()]


def make_conference_data() -> dict:
    """Create a conferenceData object for Google Meet."""
    return {
        "createRequest": {
            "requestId": str(uuid.uuid4()),
            "conferenceSolutionKey": {"type": "hangoutsMeet"},
        }
    }


# -- Auth ----------------------------------------------------------------------

def cmd_auth(token: str):
    """Verify the token works by listing calendars."""
    result = api_request(token, "GET", "/users/me/calendarList", params={"maxResults": "1"})
    items = result.get("items", []) if isinstance(result, dict) else []
    return {
        "status": "ok",
        "message": "Authentication successful",
        "primary_calendar": items[0].get("summary", "") if items else "unknown",
    }


# -- Event commands ------------------------------------------------------------

def event_list(token: str, time_min: str, time_max: str, calendar: str = "primary",
               query: str = "", single_events: bool = True, max_items: int = 50):
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": str(single_events).lower(),
    }
    if single_events:
        params["orderBy"] = "startTime"
    if query:
        params["q"] = query
    return paginate(token, f"/calendars/{calendar}/events", params, max_items)


def event_get(token: str, event_id: str, calendar: str = "primary"):
    return api_request(token, "GET", f"/calendars/{calendar}/events/{event_id}")


def event_create(token: str, summary: str, start: str, end: str,
                 calendar: str = "primary", description: str = "",
                 location: str = "", attendees: str = "",
                 meet: bool = False, send_updates: str = "all"):
    body: dict = {
        "summary": summary,
        "start": parse_datetime(start),
        "end": parse_datetime(end),
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = parse_emails(attendees)
    if meet:
        body["conferenceData"] = make_conference_data()

    params = {"sendUpdates": send_updates}
    if meet:
        params["conferenceDataVersion"] = "1"

    return api_request(token, "POST", f"/calendars/{calendar}/events", body=body, params=params)


def event_update(token: str, event_id: str, calendar: str = "primary",
                 summary: str | None = None, start: str | None = None,
                 end: str | None = None, description: str | None = None,
                 location: str | None = None, attendees: str | None = None,
                 add_attendees: str | None = None, meet: bool = False,
                 send_updates: str = "all"):
    # Fetch existing event to support merge operations (add-attendees, meet)
    existing = None
    if add_attendees or meet:
        existing = api_request(token, "GET", f"/calendars/{calendar}/events/{event_id}")

    body: dict = {}
    if summary is not None:
        body["summary"] = summary
    if start is not None:
        body["start"] = parse_datetime(start)
    if end is not None:
        body["end"] = parse_datetime(end)
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location

    # Replace attendees entirely
    if attendees is not None:
        body["attendees"] = parse_emails(attendees)

    # Merge: add new attendees to existing list
    if add_attendees and existing:
        current = existing.get("attendees", [])
        new_emails = {e.strip() for e in add_attendees.split(",") if e.strip()}
        existing_emails = {a.get("email", "") for a in current}
        for email in new_emails:
            if email not in existing_emails:
                current.append({"email": email})
        body["attendees"] = current

    # Add Meet if not already present
    if meet and existing:
        has_meet = bool(existing.get("conferenceData", {}).get("entryPoints"))
        if not has_meet:
            body["conferenceData"] = make_conference_data()

    params = {"sendUpdates": send_updates}
    if meet:
        params["conferenceDataVersion"] = "1"

    return api_request(token, "PATCH", f"/calendars/{calendar}/events/{event_id}",
                       body=body, params=params)


def event_delete(token: str, event_id: str, calendar: str = "primary",
                 send_updates: str = "all"):
    return api_request(token, "DELETE", f"/calendars/{calendar}/events/{event_id}",
                       params={"sendUpdates": send_updates})


# -- Calendar commands ---------------------------------------------------------

def calendar_list(token: str, max_items: int = 100):
    return paginate(token, "/users/me/calendarList", max_items=max_items)


# -- FreeBusy commands ---------------------------------------------------------

def freebusy_check(token: str, emails: str, time_min: str, time_max: str):
    items = [{"id": e.strip()} for e in emails.split(",") if e.strip()]
    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": items,
    }
    return api_request(token, "POST", "/freeBusy/query", body=body)


# -- CLI -----------------------------------------------------------------------

def output(data):
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def ensure_rfc3339(value: str) -> str:
    """Ensure a date or datetime string is in RFC3339 format for API params.

    Accepts YYYY-MM-DD (converts to start-of-day) or full RFC3339.
    """
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return f"{value}T00:00:00"
    return value


def main():
    parser = argparse.ArgumentParser(description="Google Calendar API CLI")
    sub = parser.add_subparsers(dest="command")

    # auth
    sub.add_parser("auth", help="Verify OAuth credentials")

    # event
    event_p = sub.add_parser("event")
    event_sub = event_p.add_subparsers(dest="event_cmd")

    p = event_sub.add_parser("list")
    p.add_argument("--from", dest="time_from", required=True, help="Start time (RFC3339 or YYYY-MM-DD)")
    p.add_argument("--to", dest="time_to", required=True, help="End time (RFC3339 or YYYY-MM-DD)")
    p.add_argument("--calendar", default="primary")
    p.add_argument("--q", default="", help="Text search query")
    p.add_argument("--no-single-events", action="store_true", help="Show recurring event masters")
    p.add_argument("--max", type=int, default=50)

    p = event_sub.add_parser("get")
    p.add_argument("event_id")
    p.add_argument("--calendar", default="primary")

    p = event_sub.add_parser("create")
    p.add_argument("--summary", required=True)
    p.add_argument("--start", required=True, help="Start time (RFC3339 or YYYY-MM-DD)")
    p.add_argument("--end", required=True, help="End time (RFC3339 or YYYY-MM-DD)")
    p.add_argument("--calendar", default="primary")
    p.add_argument("--description", default="")
    p.add_argument("--location", default="")
    p.add_argument("--attendees", default="", help="Comma-separated emails")
    p.add_argument("--meet", action="store_true", help="Add Google Meet link")
    p.add_argument("--send-updates", default="all", choices=["all", "externalOnly", "none"])

    p = event_sub.add_parser("update")
    p.add_argument("event_id")
    p.add_argument("--calendar", default="primary")
    p.add_argument("--summary", default=None)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--location", default=None)
    p.add_argument("--attendees", default=None, help="Replace all attendees (comma-separated emails)")
    p.add_argument("--add-attendees", default=None, help="Add attendees to existing list (comma-separated)")
    p.add_argument("--meet", action="store_true", help="Add Google Meet if not present")
    p.add_argument("--send-updates", default="all", choices=["all", "externalOnly", "none"])

    p = event_sub.add_parser("delete")
    p.add_argument("event_id")
    p.add_argument("--calendar", default="primary")
    p.add_argument("--send-updates", default="all", choices=["all", "externalOnly", "none"])

    # calendar
    cal_p = sub.add_parser("calendar")
    cal_sub = cal_p.add_subparsers(dest="cal_cmd")

    p = cal_sub.add_parser("list")
    p.add_argument("--max", type=int, default=100)

    # freebusy
    fb_p = sub.add_parser("freebusy")
    fb_sub = fb_p.add_subparsers(dest="fb_cmd")

    p = fb_sub.add_parser("check")
    p.add_argument("--emails", required=True, help="Comma-separated emails or calendar IDs")
    p.add_argument("--start", required=True, help="Start time (RFC3339)")
    p.add_argument("--end", required=True, help="End time (RFC3339)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    token = load_and_refresh_token()

    if args.command == "auth":
        output(cmd_auth(token))

    elif args.command == "event":
        cmd = args.event_cmd
        if cmd == "list":
            output(event_list(
                token,
                time_min=ensure_rfc3339(args.time_from),
                time_max=ensure_rfc3339(args.time_to),
                calendar=args.calendar,
                query=args.q,
                single_events=not args.no_single_events,
                max_items=args.max,
            ))
        elif cmd == "get":
            output(event_get(token, args.event_id, args.calendar))
        elif cmd == "create":
            output(event_create(
                token,
                summary=args.summary,
                start=args.start,
                end=args.end,
                calendar=args.calendar,
                description=args.description,
                location=args.location,
                attendees=args.attendees,
                meet=args.meet,
                send_updates=args.send_updates,
            ))
        elif cmd == "update":
            output(event_update(
                token,
                event_id=args.event_id,
                calendar=args.calendar,
                summary=args.summary,
                start=args.start,
                end=args.end,
                description=args.description,
                location=args.location,
                attendees=args.attendees,
                add_attendees=args.add_attendees,
                meet=args.meet,
                send_updates=args.send_updates,
            ))
        elif cmd == "delete":
            output(event_delete(token, args.event_id, args.calendar, args.send_updates))
        else:
            event_p.print_help()

    elif args.command == "calendar":
        cmd = args.cal_cmd
        if cmd == "list":
            output(calendar_list(token, args.max))
        else:
            cal_p.print_help()

    elif args.command == "freebusy":
        cmd = args.fb_cmd
        if cmd == "check":
            output(freebusy_check(
                token,
                emails=args.emails,
                start=ensure_rfc3339(args.start),
                end=ensure_rfc3339(args.end),
            ))
        else:
            fb_p.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
