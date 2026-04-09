#!/usr/bin/env python3
"""
Search Slack messages.

Usage:
    python search_messages.py <query> [options]

Options:
    --sort score|timestamp   Sort order (default: score)
    --sort-dir asc|desc      Sort direction (default: desc)
    --count N                Results per page (default: 20, max: 100)
    --page N                 Page number (default: 1)
    --json                   Output raw JSON

Examples:
    python search_messages.py "deploy error"
    python search_messages.py "in:#general from:@user bug" --sort timestamp
    python search_messages.py "has:link after:2024-01-01" --count 50 --json

Query modifiers:
    in:#channel       Search in specific channel
    from:@user        From specific user
    has:link/star/reaction/pin  Has specific attribute
    before:YYYY-MM-DD / after:YYYY-MM-DD  Date range
    during:month/week/yesterday/today  Relative date
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slack import api_call


def format_match(match):
    channel = match.get("channel", {}).get("name", "?")
    user = match.get("username", match.get("user", "?"))
    ts = match.get("ts", "")
    text = match.get("text", "")
    permalink = match.get("permalink", "")
    return f"[#{channel}] [{ts}] <{user}> {text}\n  {permalink}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search Slack messages")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--sort", default="score", choices=["score", "timestamp"])
    parser.add_argument("--sort-dir", default="desc", choices=["asc", "desc"])
    parser.add_argument("--count", type=int, default=20, help="Results per page (max 100)")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    result = api_call(
        "search.messages",
        query=args.query,
        sort=args.sort,
        sort_dir=args.sort_dir,
        count=args.count,
        page=args.page,
    )

    messages = result.get("messages", {})
    matches = messages.get("matches", [])
    total = messages.get("total", 0)
    paging = messages.get("paging", {})

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Found {total} results (page {paging.get('page', 1)}/{paging.get('pages', 1)})")
        print()
        for m in matches:
            print(format_match(m))
            print()
