#!/usr/bin/env python3
"""
Read channel/DM message history with optional thread expansion.

Usage:
    python read_history.py <channel_id> [options]

Options:
    --threads        Include full thread replies for each message
    --limit N        Max messages to fetch (default: 50)
    --oldest TS      Start from this Unix timestamp
    --latest TS      Up to this Unix timestamp
    --json           Output raw JSON (default: human-readable text)

Examples:
    python read_history.py C12345ABC --threads --limit 20
    python read_history.py D98765XYZ --json --oldest 1711324800
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slack import api_call


def read_history(channel_id, include_threads=False, limit=50, oldest=None, latest=None):
    params = {"channel": channel_id, "limit": min(limit, 200)}
    if oldest:
        params["oldest"] = oldest
    if latest:
        params["latest"] = latest

    data = api_call("conversations.history", paginate_key="messages", **params)
    messages = data.get("messages", [])[:limit]

    if include_threads:
        for msg in messages:
            if msg.get("reply_count", 0) > 0:
                thread = api_call(
                    "conversations.replies",
                    paginate_key="messages",
                    channel=channel_id,
                    ts=msg["ts"],
                    limit=200,
                )
                # First message in replies is the parent; skip it
                msg["thread_replies"] = thread.get("messages", [])[1:]

    return messages


def format_message(msg, indent=0):
    prefix = "  " * indent
    user = msg.get("user", msg.get("bot_id", "unknown"))
    ts = msg.get("ts", "")
    text = msg.get("text", "")
    reply_count = msg.get("reply_count", 0)
    lines = [f"{prefix}[{ts}] <{user}> {text}"]
    if reply_count and "thread_replies" not in msg:
        lines.append(f"{prefix}  ({reply_count} replies - use --threads to expand)")
    for reply in msg.get("thread_replies", []):
        lines.append(format_message(reply, indent + 1))
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read Slack channel/DM history")
    parser.add_argument("channel_id", help="Channel or DM ID (e.g. C12345ABC)")
    parser.add_argument("--threads", action="store_true", help="Include thread replies")
    parser.add_argument("--limit", type=int, default=50, help="Max messages (default: 50)")
    parser.add_argument("--oldest", help="Start Unix timestamp")
    parser.add_argument("--latest", help="End Unix timestamp")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    messages = read_history(
        args.channel_id, args.threads, args.limit, args.oldest, args.latest
    )

    if args.json:
        print(json.dumps(messages, indent=2, ensure_ascii=False))
    else:
        for msg in reversed(messages):  # chronological order
            print(format_message(msg))
            print()
