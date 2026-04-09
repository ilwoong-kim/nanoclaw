#!/usr/bin/env python3
"""Atlassian Cloud REST API helper — Jira + Confluence.

Usage:
    # Setup credentials (interactive)
    python atlassian_api.py setup

    # Check credential status / expiry
    python atlassian_api.py status

    # Jira: Get issue
    python atlassian_api.py jira get-issue ARK-307

    # Jira: Search (JQL)
    python atlassian_api.py jira search 'project = ARK AND status = "In Progress"'

    # Jira: Create issue
    python atlassian_api.py jira create-issue --project ARK --type Task --summary "Title" --description "Body"

    # Jira: Transition issue
    python atlassian_api.py jira transition ARK-100 "Done"

    # Jira: Add comment
    python atlassian_api.py jira add-comment ARK-100 "comment text"

    # Confluence: List spaces
    python atlassian_api.py confluence list-spaces

    # Confluence: Get page
    python atlassian_api.py confluence get-page 12345

    # Confluence: Search (CQL)
    python atlassian_api.py confluence search 'type = page AND space = "MYSPACE" AND title ~ "keyword"'

    # Confluence: Create page
    python atlassian_api.py confluence create-page --space-id 12345 --title "Title" --body "<p>content</p>"

Environment:
    Reads credentials from macOS Keychain (service: atlassian-credentials).
    Override with env vars: ATLASSIAN_DOMAIN, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

KEYCHAIN_SERVICE = "atlassian-credentials"


# ── Credentials ──────────────────────────────────────────────────────────────

def _keychain_load() -> dict:
    """Read credentials JSON from macOS Keychain. Returns {} if missing."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-a", os.environ.get("USER", ""),
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return {}


def load_credentials() -> dict:
    """Load credentials from macOS Keychain, with environment variable override."""
    creds = _keychain_load()
    return {
        "domain": os.environ.get("ATLASSIAN_DOMAIN", creds.get("domain", "")),
        "email": os.environ.get("ATLASSIAN_EMAIL", creds.get("email", "")),
        "api_token": os.environ.get("ATLASSIAN_API_TOKEN", creds.get("api_token", "")),
        "created_at": creds.get("created_at", ""),
        "expires_at": creds.get("expires_at", ""),
    }


def save_credentials(domain: str, email: str, api_token: str):
    """Save credentials with creation/expiry metadata to macOS Keychain."""
    now = datetime.now(timezone.utc)
    data = {
        "domain": domain,
        "email": email,
        "api_token": api_token,
        "created_at": now.isoformat(),
        "expires_at": (now.replace(year=now.year + 1)).isoformat(),
        "note": "API token expires ~1 year from creation. Regenerate at https://id.atlassian.com/manage-profile/security/api-tokens",
    }
    payload = json.dumps(data, separators=(",", ":"))  # single-line; security CLI treats newlines as binary
    subprocess.run(
        ["security", "add-generic-password", "-U",
         "-a", os.environ.get("USER", ""),
         "-s", KEYCHAIN_SERVICE,
         "-w", payload],
        check=True,
    )
    print(f"Credentials saved to Keychain (service: {KEYCHAIN_SERVICE})")


def check_expiry(creds: dict) -> str | None:
    """Return warning message if token is expiring soon or expired."""
    expires_at = creds.get("expires_at")
    if not expires_at:
        return None
    try:
        exp = datetime.fromisoformat(expires_at)
        now = datetime.now(timezone.utc)
        days_left = (exp - now).days
        rotate_hint = (
            "To rotate: see 'Token Rotation Procedure' in "
            "~/.claude/skills/atlassian/SKILL.md "
            "(or run `python ~/.claude/skills/atlassian/scripts/atlassian_api.py setup` "
            "after generating a new token at "
            "https://id.atlassian.com/manage-profile/security/api-tokens)."
        )
        if days_left < 0:
            return f"API token EXPIRED {abs(days_left)} days ago! {rotate_hint}"
        if days_left < 30:
            return f"API token expires in {days_left} days. {rotate_hint}"
        return None
    except (ValueError, TypeError):
        return None


def validate_credentials(creds: dict):
    """Validate that required credentials are present."""
    missing = [k for k in ("domain", "email", "api_token") if not creds.get(k)]
    if missing:
        print(f"Missing credentials: {', '.join(missing)}")
        print(f"Run: python {__file__} setup")
        print(f"Or set env vars: ATLASSIAN_DOMAIN, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN")
        sys.exit(1)
    warning = check_expiry(creds)
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)


# ── HTTP ─────────────────────────────────────────────────────────────────────

def api_request(
    creds: dict,
    method: str,
    path: str,
    body: dict | None = None,
    headers: dict | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
) -> dict | list | str:
    """Make an authenticated API request. Returns parsed JSON or status message."""
    base_url = f"https://{creds['domain']}.atlassian.net"
    url = f"{base_url}{path}"

    auth_str = base64.b64encode(f"{creds['email']}:{creds['api_token']}".encode()).decode()
    req_headers = {
        "Authorization": f"Basic {auth_str}",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)

    data = None
    if raw_body:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode()
        req_headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

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


def paginate_jira(creds: dict, path: str, params: dict | None = None, max_results: int = 100) -> list:
    """Paginate through Jira results using nextPageToken."""
    params = dict(params or {})
    params["maxResults"] = min(max_results, 100)
    all_items = []

    while True:
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in path else "?"
        result = api_request(creds, "GET", f"{path}{sep}{query}")
        items = result.get("issues") or result.get("values") or result.get("results") or []
        all_items.extend(items)
        token = result.get("nextPageToken")
        if not token or len(all_items) >= max_results:
            break
        params["nextPageToken"] = token

    return all_items[:max_results]


def paginate_confluence_v2(creds: dict, path: str, params: dict | None = None, max_results: int = 100) -> list:
    """Paginate through Confluence v2 results using cursor."""
    params = dict(params or {})
    params["limit"] = min(max_results, 250)
    all_items = []

    while True:
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in path else "?"
        result = api_request(creds, "GET", f"{path}{sep}{query}")
        items = result.get("results", [])
        all_items.extend(items)
        next_link = result.get("_links", {}).get("next")
        if not next_link or len(all_items) >= max_results:
            break
        # next_link is a relative URL with cursor param
        path = next_link.split("?")[0] if "?" in next_link else next_link
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(next_link).query))

    return all_items[:max_results]


# ── ADF Helper ───────────────────────────────────────────────────────────────

def text_to_adf(text: str) -> dict:
    """Convert plain text to Atlassian Document Format."""
    paragraphs = text.split("\n\n") if "\n\n" in text else [text]
    content = []
    for p in paragraphs:
        content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": p.strip()}],
        })
    return {"type": "doc", "version": 1, "content": content}


# ── Jira Commands ────────────────────────────────────────────────────────────

def jira_get_issue(creds: dict, issue_key: str, fields: str | None = None):
    params = f"?fields={fields}" if fields else ""
    return api_request(creds, "GET", f"/rest/api/3/issue/{issue_key}{params}")


def jira_search(creds: dict, jql: str, fields: str = "summary,status,assignee,priority", max_results: int = 50):
    params = {"jql": jql, "fields": fields}
    return paginate_jira(creds, "/rest/api/3/search/jql", params, max_results)


def jira_create_issue(creds: dict, project: str, issue_type: str, summary: str, description: str = "",
                       parent: str | None = None, assignee: str | None = None, labels: list | None = None,
                       priority: str | None = None):
    fields = {
        "project": {"key": project},
        "issuetype": {"name": issue_type},
        "summary": summary,
    }
    if description:
        fields["description"] = text_to_adf(description)
    if parent:
        fields["parent"] = {"key": parent}
    if assignee:
        fields["assignee"] = {"accountId": assignee}
    if labels:
        fields["labels"] = labels
    if priority:
        fields["priority"] = {"name": priority}
    return api_request(creds, "POST", "/rest/api/3/issue", {"fields": fields})


def jira_edit_issue(creds: dict, issue_key: str, fields: dict | None = None, update: dict | None = None):
    body = {}
    if fields:
        body["fields"] = fields
    if update:
        body["update"] = update
    return api_request(creds, "PUT", f"/rest/api/3/issue/{issue_key}", body)


def jira_delete_issue(creds: dict, issue_key: str, delete_subtasks: bool = False):
    params = "?deleteSubtasks=true" if delete_subtasks else ""
    return api_request(creds, "DELETE", f"/rest/api/3/issue/{issue_key}{params}")


def jira_get_transitions(creds: dict, issue_key: str):
    return api_request(creds, "GET", f"/rest/api/3/issue/{issue_key}/transitions")


def jira_transition(creds: dict, issue_key: str, transition_name: str):
    transitions = jira_get_transitions(creds, issue_key)
    match = None
    for t in transitions.get("transitions", []):
        if t["name"].lower() == transition_name.lower():
            match = t
            break
    if not match:
        available = [t["name"] for t in transitions.get("transitions", [])]
        print(f"Transition '{transition_name}' not found. Available: {available}", file=sys.stderr)
        sys.exit(1)
    return api_request(creds, "POST", f"/rest/api/3/issue/{issue_key}/transitions",
                       {"transition": {"id": match["id"]}})


def jira_add_comment(creds: dict, issue_key: str, text: str):
    return api_request(creds, "POST", f"/rest/api/3/issue/{issue_key}/comment",
                       {"body": text_to_adf(text)})


def jira_get_comments(creds: dict, issue_key: str):
    return api_request(creds, "GET", f"/rest/api/3/issue/{issue_key}/comment")


def jira_list_projects(creds: dict):
    return api_request(creds, "GET", "/rest/api/3/project/search?maxResults=50")


def jira_myself(creds: dict):
    return api_request(creds, "GET", "/rest/api/3/myself")


def jira_search_users(creds: dict, query: str):
    return api_request(creds, "GET", f"/rest/api/3/user/search?query={urllib.parse.quote(query)}")


# ── Confluence Commands ──────────────────────────────────────────────────────

def confluence_list_spaces(creds: dict, limit: int = 25):
    return paginate_confluence_v2(creds, "/wiki/api/v2/spaces", {"limit": limit}, limit)


def confluence_get_space(creds: dict, space_id: str):
    return api_request(creds, "GET", f"/wiki/api/v2/spaces/{space_id}?description-format=plain")


def confluence_get_page(creds: dict, page_id: str, body_format: str = "storage"):
    return api_request(creds, "GET", f"/wiki/api/v2/pages/{page_id}?body-format={body_format}")


def confluence_list_pages(creds: dict, space_id: str | None = None, title: str | None = None, limit: int = 25):
    params = {}
    if space_id:
        params["space-id"] = space_id
    if title:
        params["title"] = title
    return paginate_confluence_v2(creds, "/wiki/api/v2/pages", params, limit)


def confluence_create_page(creds: dict, space_id: str, title: str, body: str,
                            parent_id: str | None = None, representation: str = "storage"):
    data = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {"representation": representation, "value": body},
    }
    if parent_id:
        data["parentId"] = parent_id
    return api_request(creds, "POST", "/wiki/api/v2/pages", data)


def confluence_update_page(creds: dict, page_id: str, title: str, body: str,
                            version_number: int, representation: str = "storage"):
    data = {
        "id": page_id,
        "status": "current",
        "title": title,
        "body": {"representation": representation, "value": body},
        "version": {"number": version_number, "message": "Updated via API"},
    }
    return api_request(creds, "PUT", f"/wiki/api/v2/pages/{page_id}", data)


def confluence_delete_page(creds: dict, page_id: str):
    return api_request(creds, "DELETE", f"/wiki/api/v2/pages/{page_id}")


def confluence_search(creds: dict, cql: str, limit: int = 25, expand: str = ""):
    params = f"?cql={urllib.parse.quote(cql)}&limit={limit}"
    if expand:
        params += f"&expand={expand}"
    return api_request(creds, "GET", f"/wiki/rest/api/search{params}")


def confluence_get_comments(creds: dict, page_id: str):
    return paginate_confluence_v2(creds, f"/wiki/api/v2/pages/{page_id}/footer-comments",
                                  {"body-format": "storage"}, 50)


def confluence_add_comment(creds: dict, page_id: str, body: str, representation: str = "storage"):
    return api_request(creds, "POST", "/wiki/api/v2/footer-comments", {
        "pageId": page_id,
        "body": {"representation": representation, "value": body},
    })


def confluence_add_labels(creds: dict, content_id: str, labels: list[str]):
    """Add labels (v1 API — v2 doesn't support label writes)."""
    label_data = [{"prefix": "global", "name": l} for l in labels]
    return api_request(creds, "POST", f"/wiki/rest/api/content/{content_id}/label", label_data)


def confluence_remove_label(creds: dict, content_id: str, label: str):
    """Remove a label (v1 API)."""
    return api_request(creds, "DELETE",
                       f"/wiki/rest/api/content/{content_id}/label?name={urllib.parse.quote(label)}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_setup(_args):
    print("Atlassian API Credentials Setup")
    print("=" * 40)
    print("Generate a token at: https://id.atlassian.com/manage-profile/security/api-tokens\n")
    domain = input("Atlassian domain (e.g., 'quantit' for quantit.atlassian.net): ").strip()
    email = input("Email: ").strip()
    api_token = input("API Token: ").strip()
    if not all([domain, email, api_token]):
        print("All fields required.")
        sys.exit(1)
    save_credentials(domain, email, api_token)
    print("\nVerifying credentials...")
    creds = load_credentials()
    result = jira_myself(creds)
    print(f"Authenticated as: {result.get('displayName')} ({result.get('emailAddress')})")


def cmd_status(_args):
    creds = load_credentials()
    if not creds.get("domain"):
        print(f"No credentials found. Run: python {__file__} setup")
        return
    print(f"Domain:     {creds['domain']}.atlassian.net")
    print(f"Email:      {creds['email']}")
    print(f"Created:    {creds.get('created_at', 'unknown')}")
    print(f"Expires:    {creds.get('expires_at', 'unknown')}")
    warning = check_expiry(creds)
    if warning:
        print(f"\nWARNING: {warning}")
    else:
        expires = creds.get("expires_at")
        if expires:
            days_left = (datetime.fromisoformat(expires) - datetime.now(timezone.utc)).days
            print(f"Status:     Valid ({days_left} days remaining)")


def output(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Atlassian Cloud REST API CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Configure credentials")
    sub.add_parser("status", help="Check credential status")

    # Jira subcommands
    jira_parser = sub.add_parser("jira")
    jira_sub = jira_parser.add_subparsers(dest="jira_cmd")

    p = jira_sub.add_parser("get-issue")
    p.add_argument("key")
    p.add_argument("--fields", default=None)

    p = jira_sub.add_parser("search")
    p.add_argument("jql")
    p.add_argument("--fields", default="summary,status,assignee,priority")
    p.add_argument("--max", type=int, default=50)

    p = jira_sub.add_parser("create-issue")
    p.add_argument("--project", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--parent", default=None)
    p.add_argument("--assignee", default=None)
    p.add_argument("--labels", nargs="*", default=None)
    p.add_argument("--priority", default=None)

    p = jira_sub.add_parser("edit-issue")
    p.add_argument("key")
    p.add_argument("--summary", default=None)
    p.add_argument("--add-labels", nargs="*", default=None)
    p.add_argument("--remove-labels", nargs="*", default=None)

    p = jira_sub.add_parser("delete-issue")
    p.add_argument("key")
    p.add_argument("--delete-subtasks", action="store_true")

    p = jira_sub.add_parser("transitions")
    p.add_argument("key")

    p = jira_sub.add_parser("transition")
    p.add_argument("key")
    p.add_argument("name")

    p = jira_sub.add_parser("add-comment")
    p.add_argument("key")
    p.add_argument("text")

    p = jira_sub.add_parser("get-comments")
    p.add_argument("key")

    p = jira_sub.add_parser("list-projects")

    p = jira_sub.add_parser("myself")

    p = jira_sub.add_parser("search-users")
    p.add_argument("query")

    # Confluence subcommands
    conf_parser = sub.add_parser("confluence")
    conf_sub = conf_parser.add_subparsers(dest="conf_cmd")

    conf_sub.add_parser("list-spaces")

    p = conf_sub.add_parser("get-space")
    p.add_argument("id")

    p = conf_sub.add_parser("get-page")
    p.add_argument("id")
    p.add_argument("--body-format", default="storage")

    p = conf_sub.add_parser("list-pages")
    p.add_argument("--space-id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--limit", type=int, default=25)

    p = conf_sub.add_parser("create-page")
    p.add_argument("--space-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--parent-id", default=None)

    p = conf_sub.add_parser("update-page")
    p.add_argument("id")
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--version", type=int, required=True)

    p = conf_sub.add_parser("delete-page")
    p.add_argument("id")

    p = conf_sub.add_parser("search")
    p.add_argument("cql")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--expand", default="")

    p = conf_sub.add_parser("get-comments")
    p.add_argument("id")

    p = conf_sub.add_parser("add-comment")
    p.add_argument("page_id")
    p.add_argument("body")

    p = conf_sub.add_parser("add-labels")
    p.add_argument("content_id")
    p.add_argument("labels", nargs="+")

    p = conf_sub.add_parser("remove-label")
    p.add_argument("content_id")
    p.add_argument("label")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "jira":
        creds = load_credentials()
        validate_credentials(creds)
        cmd = args.jira_cmd
        if cmd == "get-issue":
            output(jira_get_issue(creds, args.key, args.fields))
        elif cmd == "search":
            output(jira_search(creds, args.jql, args.fields, args.max))
        elif cmd == "create-issue":
            output(jira_create_issue(creds, args.project, args.type, args.summary,
                                     args.description, args.parent, args.assignee, args.labels, args.priority))
        elif cmd == "edit-issue":
            fields = {}
            update = {}
            if args.summary:
                fields["summary"] = args.summary
            if args.add_labels:
                update["labels"] = [{"add": l} for l in args.add_labels]
            if args.remove_labels:
                update.setdefault("labels", []).extend([{"remove": l} for l in args.remove_labels])
            output(jira_edit_issue(creds, args.key, fields or None, update or None))
        elif cmd == "delete-issue":
            output(jira_delete_issue(creds, args.key, args.delete_subtasks))
        elif cmd == "transitions":
            output(jira_get_transitions(creds, args.key))
        elif cmd == "transition":
            output(jira_transition(creds, args.key, args.name))
        elif cmd == "add-comment":
            output(jira_add_comment(creds, args.key, args.text))
        elif cmd == "get-comments":
            output(jira_get_comments(creds, args.key))
        elif cmd == "list-projects":
            output(jira_list_projects(creds))
        elif cmd == "myself":
            output(jira_myself(creds))
        elif cmd == "search-users":
            output(jira_search_users(creds, args.query))
    elif args.command == "confluence":
        creds = load_credentials()
        validate_credentials(creds)
        cmd = args.conf_cmd
        if cmd == "list-spaces":
            output(confluence_list_spaces(creds))
        elif cmd == "get-space":
            output(confluence_get_space(creds, args.id))
        elif cmd == "get-page":
            output(confluence_get_page(creds, args.id, args.body_format))
        elif cmd == "list-pages":
            output(confluence_list_pages(creds, args.space_id, args.title, args.limit))
        elif cmd == "create-page":
            output(confluence_create_page(creds, args.space_id, args.title, args.body, args.parent_id))
        elif cmd == "update-page":
            output(confluence_update_page(creds, args.id, args.title, args.body, args.version))
        elif cmd == "delete-page":
            output(confluence_delete_page(creds, args.id))
        elif cmd == "search":
            output(confluence_search(creds, args.cql, args.limit, args.expand))
        elif cmd == "get-comments":
            output(confluence_get_comments(creds, args.id))
        elif cmd == "add-comment":
            output(confluence_add_comment(creds, args.page_id, args.body))
        elif cmd == "add-labels":
            output(confluence_add_labels(creds, args.content_id, args.labels))
        elif cmd == "remove-label":
            output(confluence_remove_label(creds, args.content_id, args.label))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
