#!/usr/bin/env python3
"""
Slack Web API caller with automatic cursor-based pagination and rate-limit handling.
Uses only Python stdlib (no external dependencies).

Read methods use SLACK_USER_TOKEN (personal scope), write methods use
SLACK_BOT_TOKEN (Luffy-Bot identity).  Token selection is enforced at the
code level — callers cannot override it.

As a module:
    from slack import api_call
    result = api_call("conversations.list", paginate_key="channels", types="public_channel")

As CLI:
    python slack.py <method> [key=value ...] [--paginate <response_key>]

Examples:
    python slack.py conversations.list types=public_channel,private_channel --paginate channels
    python slack.py conversations.history channel=C12345 limit=20 --paginate messages
    python slack.py users.info user=U12345
    python slack.py reactions.add channel=C12345 name=thumbsup timestamp=1234567890.123456
    python slack.py auth.test

Environment:
    SLACK_USER_TOKEN  - Slack User OAuth Token (xoxp-...) for read operations
    SLACK_BOT_TOKEN   - Slack Bot OAuth Token (xoxb-...) for write operations
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


USER_TOKEN = os.environ.get("SLACK_USER_TOKEN", "")
BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
BASE_URL = "https://slack.com/api"

# Slack API methods that only accept GET with query parameters.
# POST with JSON body silently ignores params for these methods.
_GET_METHODS = frozenset({
    "conversations.history",
    "conversations.info",
    "conversations.list",
    "conversations.members",
    "conversations.replies",
    "users.conversations",
    "users.info",
    "users.list",
    "users.lookupByEmail",
    "search.messages",
    "search.files",
    "search.all",
    "pins.list",
    "reactions.list",
    "reactions.get",
    "stars.list",
    "files.info",
    "files.list",
    "bookmarks.list",
    "reminders.info",
    "reminders.list",
    "team.info",
    "usergroups.list",
    "usergroups.users.list",
})

# Read methods — always use User Token (personal scope).
_READ_METHODS = _GET_METHODS | frozenset({
    "auth.test",
})

# Write methods — always use Bot Token (Luffy-Bot identity).
_WRITE_METHODS = frozenset({
    # Messages
    "chat.postMessage",
    "chat.update",
    "chat.delete",
    "chat.postEphemeral",
    # Reactions
    "reactions.add",
    "reactions.remove",
    # Pins
    "pins.add",
    "pins.remove",
    # Bookmarks
    "bookmarks.add",
    "bookmarks.edit",
    "bookmarks.remove",
    # Channel management
    "conversations.invite",
    "conversations.kick",
    "conversations.setPurpose",
    "conversations.setTopic",
    "conversations.open",
    "conversations.close",
    "conversations.archive",
    "conversations.unarchive",
    # Reminders
    "reminders.add",
    "reminders.delete",
    "reminders.complete",
})

_ALLOWED_METHODS = _READ_METHODS | _WRITE_METHODS


def _token_for(method):
    """Return the correct token for the given method.

    Write methods → BOT_TOKEN (enforced), read methods → USER_TOKEN (preferred).
    This function is the single enforcement point — callers cannot choose a token.
    """
    if method in _WRITE_METHODS:
        if not BOT_TOKEN:
            print(
                f"Error: SLACK_BOT_TOKEN is required for write method '{method}'.",
                file=sys.stderr,
            )
            sys.exit(1)
        return BOT_TOKEN
    # Read method
    if USER_TOKEN:
        return USER_TOKEN
    if BOT_TOKEN:
        print(
            f"Warning: SLACK_USER_TOKEN not set, falling back to BOT_TOKEN "
            f"for read method '{method}'. Some methods (e.g. search) may not work.",
            file=sys.stderr,
        )
        return BOT_TOKEN
    print(
        "Error: SLACK_USER_TOKEN (or SLACK_BOT_TOKEN as fallback) "
        "is required for read operations.",
        file=sys.stderr,
    )
    sys.exit(1)


def _request(url, headers, data=None, method="POST"):
    """Send a single HTTP request and return parsed JSON. Handles 429."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    while True:
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 5))
                print(f"Rate limited. Waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {body}", file=sys.stderr)
            sys.exit(1)


def api_call(method, paginate_key=None, **params):
    """Call a Slack Web API method.

    Args:
        method: Slack API method name (e.g. "conversations.history")
        paginate_key: If set, follow cursor-based pagination and collect
                      all items under this response key.
        **params: Method parameters.

    Returns:
        The JSON response dict. If paginate_key is used, the specified key
        contains all collected items across pages.
    """
    if method not in _ALLOWED_METHODS:
        print(
            f"Error: '{method}' is not a supported method.",
            file=sys.stderr,
        )
        sys.exit(1)

    token = _token_for(method)
    use_get = method in _GET_METHODS
    all_items = []
    cursor = None

    while True:
        call_params = dict(params)
        if cursor:
            call_params["cursor"] = cursor

        if use_get:
            qs = urllib.parse.urlencode(call_params)
            url = f"{BASE_URL}/{method}?{qs}" if qs else f"{BASE_URL}/{method}"
            headers = {"Authorization": f"Bearer {token}"}
            result = _request(url, headers, method="GET")
        else:
            url = f"{BASE_URL}/{method}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            data = json.dumps(call_params).encode("utf-8")
            result = _request(url, headers, data=data, method="POST")

        if not result.get("ok"):
            # Fallback: if POST failed with invalid_arguments, retry as GET.
            # Only for read methods — write methods must always use POST.
            if (
                not use_get
                and method not in _WRITE_METHODS
                and result.get("error") == "invalid_arguments"
            ):
                use_get = True
                continue
            print(json.dumps(result, indent=2, ensure_ascii=False))
            sys.exit(1)

        if paginate_key is None:
            return result

        all_items.extend(result.get(paginate_key, []))
        next_cursor = result.get("response_metadata", {}).get("next_cursor", "")
        if not next_cursor:
            result[paginate_key] = all_items
            return result

        cursor = next_cursor


def _parse_value(v):
    """Parse CLI value: try JSON first (numbers, bools, arrays), fallback to string."""
    try:
        return json.loads(v)
    except (json.JSONDecodeError, ValueError):
        return v


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    method = args[0]
    params = {}
    paginate_key = None
    i = 1
    while i < len(args):
        if args[i] == "--paginate" and i + 1 < len(args):
            paginate_key = args[i + 1]
            i += 2
        elif "=" in args[i]:
            k, v = args[i].split("=", 1)
            params[k] = _parse_value(v)
            i += 1
        else:
            print(f"Unknown argument: {args[i]}", file=sys.stderr)
            sys.exit(1)

    result = api_call(method, paginate_key=paginate_key, **params)
    print(json.dumps(result, indent=2, ensure_ascii=False))
