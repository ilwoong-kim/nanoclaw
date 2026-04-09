#!/usr/bin/env python3
"""
List Slack conversations (channels, DMs, group DMs) the user belongs to.

Usage:
    python list_conversations.py [options]

Options:
    --types TYPES    Comma-separated types (default: public_channel,private_channel,mpim,im)
    --json           Output raw JSON

Examples:
    python list_conversations.py
    python list_conversations.py --types im --json
    python list_conversations.py --types public_channel,private_channel
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slack import api_call


def list_conversations(types="public_channel,private_channel,mpim,im"):
    data = api_call(
        "conversations.list",
        paginate_key="channels",
        types=types,
        limit=200,
    )
    return data.get("channels", [])


def resolve_im_users(conversations):
    """Resolve DM user IDs to display names."""
    im_user_ids = {c["user"] for c in conversations if c.get("is_im") and c.get("user")}
    if not im_user_ids:
        return {}

    user_map = {}
    for uid in im_user_ids:
        try:
            data = api_call("users.info", user=uid)
            u = data.get("user", {})
            user_map[uid] = u.get("real_name") or u.get("name") or uid
        except SystemExit:
            user_map[uid] = uid
    return user_map


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List Slack conversations")
    parser.add_argument(
        "--types",
        default="public_channel,private_channel,mpim,im",
        help="Conversation types (default: all)",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    convos = list_conversations(args.types)

    if args.json:
        print(json.dumps(convos, indent=2, ensure_ascii=False))
    else:
        user_map = resolve_im_users(convos)
        for c in sorted(convos, key=lambda x: x.get("name", "")):
            cid = c["id"]
            if c.get("is_im"):
                name = f"DM: {user_map.get(c.get('user', ''), c.get('user', ''))}"
            elif c.get("is_mpim"):
                name = f"Group DM: {c.get('name', cid)}"
            else:
                prefix = "private" if c.get("is_private") else "public"
                name = f"#{c.get('name', cid)} ({prefix})"
            print(f"{cid}  {name}")
