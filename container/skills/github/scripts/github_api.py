#!/usr/bin/env python3
"""GitHub REST API helper for NanoClaw container agents.

Usage:
    # Auth check
    python github_api.py auth

    # Repos
    python github_api.py repo get owner/repo
    python github_api.py repo list-branches owner/repo
    python github_api.py repo list-tags owner/repo

    # Issues
    python github_api.py issue list owner/repo
    python github_api.py issue get owner/repo 123
    python github_api.py issue create owner/repo --title "Bug" --body "Details"
    python github_api.py issue update owner/repo 123 --state closed
    python github_api.py issue comment owner/repo 123 "comment text"
    python github_api.py issue list-comments owner/repo 123

    # Pull Requests
    python github_api.py pr list owner/repo
    python github_api.py pr get owner/repo 123
    python github_api.py pr create owner/repo --title "Feature" --head branch --base main
    python github_api.py pr update owner/repo 123 --title "New title"
    python github_api.py pr merge owner/repo 123 --method squash
    python github_api.py pr diff owner/repo 123
    python github_api.py pr files owner/repo 123
    python github_api.py pr comment owner/repo 123 "comment text"
    python github_api.py pr list-comments owner/repo 123
    python github_api.py pr reviews owner/repo 123
    python github_api.py pr checks owner/repo 123

    # Releases
    python github_api.py release list owner/repo
    python github_api.py release get owner/repo tag_name
    python github_api.py release latest owner/repo
    python github_api.py release create owner/repo --tag v1.0 --name "Release 1.0" --body "Notes"

    # Actions
    python github_api.py actions workflows owner/repo
    python github_api.py actions runs owner/repo
    python github_api.py actions get-run owner/repo 123456
    python github_api.py actions rerun owner/repo 123456
    python github_api.py actions cancel owner/repo 123456
    python github_api.py actions run-workflow owner/repo workflow.yml --ref main

    # Search
    python github_api.py search repos "query"
    python github_api.py search issues "query"
    python github_api.py search code "query"

    # Gists
    python github_api.py gist list
    python github_api.py gist get gist_id
    python github_api.py gist create --description "desc" --public file1.py=content1

    # Notifications
    python github_api.py notifications [--unread]

Environment:
    GITHUB_TOKEN — Personal access token (classic) or fine-grained token
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.github.com"


# -- Credentials --------------------------------------------------------------

def load_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Missing GITHUB_TOKEN environment variable.", file=sys.stderr)
        print("Set it via OneCLI or .env on the host.", file=sys.stderr)
        sys.exit(1)
    return token


# -- HTTP ----------------------------------------------------------------------

def api_request(
    token: str,
    method: str,
    path: str,
    body: dict | None = None,
    accept: str = "application/vnd.github+json",
) -> dict | list | str:
    url = f"{API_BASE}{path}" if path.startswith("/") else path

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nanoclaw-github-skill",
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


def paginate(token: str, path: str, params: dict | None = None, max_items: int = 100) -> list:
    params = dict(params or {})
    params["per_page"] = min(max_items, 100)
    all_items = []
    page = 1

    while len(all_items) < max_items:
        params["page"] = page
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in path else "?"
        result = api_request(token, "GET", f"{path}{sep}{query}")
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            # Search endpoints wrap results
            items = result.get("items", result.get("workflow_runs", result.get("workflows", [])))
        else:
            break
        if not items:
            break
        all_items.extend(items)
        page += 1

    return all_items[:max_items]


# -- Auth ----------------------------------------------------------------------

def cmd_auth(token: str):
    return api_request(token, "GET", "/user")


# -- Repos ---------------------------------------------------------------------

def repo_get(token: str, repo: str):
    return api_request(token, "GET", f"/repos/{repo}")


def repo_list_branches(token: str, repo: str, max_items: int = 30):
    return paginate(token, f"/repos/{repo}/branches", max_items=max_items)


def repo_list_tags(token: str, repo: str, max_items: int = 30):
    return paginate(token, f"/repos/{repo}/tags", max_items=max_items)


# -- Issues --------------------------------------------------------------------

def issue_list(token: str, repo: str, state: str = "open", labels: str = "",
               assignee: str = "", max_items: int = 30):
    params = {"state": state}
    if labels:
        params["labels"] = labels
    if assignee:
        params["assignee"] = assignee
    return paginate(token, f"/repos/{repo}/issues", params, max_items)


def issue_get(token: str, repo: str, number: int):
    return api_request(token, "GET", f"/repos/{repo}/issues/{number}")


def issue_create(token: str, repo: str, title: str, body: str = "",
                 labels: list | None = None, assignees: list | None = None):
    data = {"title": title}
    if body:
        data["body"] = body
    if labels:
        data["labels"] = labels
    if assignees:
        data["assignees"] = assignees
    return api_request(token, "POST", f"/repos/{repo}/issues", data)


def issue_update(token: str, repo: str, number: int, title: str | None = None,
                 body: str | None = None, state: str | None = None,
                 labels: list | None = None, assignees: list | None = None):
    data = {}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    if state is not None:
        data["state"] = state
    if labels is not None:
        data["labels"] = labels
    if assignees is not None:
        data["assignees"] = assignees
    return api_request(token, "PATCH", f"/repos/{repo}/issues/{number}", data)


def issue_comment(token: str, repo: str, number: int, body: str):
    return api_request(token, "POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})


def issue_list_comments(token: str, repo: str, number: int, max_items: int = 30):
    return paginate(token, f"/repos/{repo}/issues/{number}/comments", max_items=max_items)


# -- Pull Requests -------------------------------------------------------------

def pr_list(token: str, repo: str, state: str = "open", base: str = "",
            head: str = "", max_items: int = 30):
    params = {"state": state}
    if base:
        params["base"] = base
    if head:
        params["head"] = head
    return paginate(token, f"/repos/{repo}/pulls", params, max_items)


def pr_get(token: str, repo: str, number: int):
    return api_request(token, "GET", f"/repos/{repo}/pulls/{number}")


def pr_create(token: str, repo: str, title: str, head: str, base: str,
              body: str = "", draft: bool = False):
    data = {"title": title, "head": head, "base": base, "body": body, "draft": draft}
    return api_request(token, "POST", f"/repos/{repo}/pulls", data)


def pr_update(token: str, repo: str, number: int, title: str | None = None,
              body: str | None = None, state: str | None = None, base: str | None = None):
    data = {}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    if state is not None:
        data["state"] = state
    if base is not None:
        data["base"] = base
    return api_request(token, "PATCH", f"/repos/{repo}/pulls/{number}", data)


def pr_merge(token: str, repo: str, number: int, method: str = "merge",
             commit_title: str = "", commit_message: str = ""):
    data = {"merge_method": method}
    if commit_title:
        data["commit_title"] = commit_title
    if commit_message:
        data["commit_message"] = commit_message
    return api_request(token, "PUT", f"/repos/{repo}/pulls/{number}/merge", data)


def pr_diff(token: str, repo: str, number: int):
    return api_request(token, "GET", f"/repos/{repo}/pulls/{number}",
                       accept="application/vnd.github.diff")


def pr_files(token: str, repo: str, number: int, max_items: int = 100):
    return paginate(token, f"/repos/{repo}/pulls/{number}/files", max_items=max_items)


def pr_comment(token: str, repo: str, number: int, body: str):
    # PR comments use the issues endpoint
    return api_request(token, "POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})


def pr_list_comments(token: str, repo: str, number: int, max_items: int = 30):
    return paginate(token, f"/repos/{repo}/pulls/{number}/comments", max_items=max_items)


def pr_reviews(token: str, repo: str, number: int, max_items: int = 30):
    return paginate(token, f"/repos/{repo}/pulls/{number}/reviews", max_items=max_items)


def pr_checks(token: str, repo: str, number: int):
    pr = api_request(token, "GET", f"/repos/{repo}/pulls/{number}")
    sha = pr.get("head", {}).get("sha", "")
    if not sha:
        return {"error": "Could not get head SHA"}
    return api_request(token, "GET", f"/repos/{repo}/commits/{sha}/check-runs")


# -- Releases ------------------------------------------------------------------

def release_list(token: str, repo: str, max_items: int = 30):
    return paginate(token, f"/repos/{repo}/releases", max_items=max_items)


def release_get(token: str, repo: str, tag: str):
    return api_request(token, "GET", f"/repos/{repo}/releases/tags/{tag}")


def release_latest(token: str, repo: str):
    return api_request(token, "GET", f"/repos/{repo}/releases/latest")


def release_create(token: str, repo: str, tag: str, name: str = "", body: str = "",
                   draft: bool = False, prerelease: bool = False, target: str = ""):
    data = {"tag_name": tag, "draft": draft, "prerelease": prerelease}
    if name:
        data["name"] = name
    if body:
        data["body"] = body
    if target:
        data["target_commitish"] = target
    return api_request(token, "POST", f"/repos/{repo}/releases", data)


# -- Actions -------------------------------------------------------------------

def actions_workflows(token: str, repo: str):
    return api_request(token, "GET", f"/repos/{repo}/actions/workflows")


def actions_runs(token: str, repo: str, workflow_id: str = "", status: str = "",
                 branch: str = "", max_items: int = 20):
    path = f"/repos/{repo}/actions/workflows/{workflow_id}/runs" if workflow_id else f"/repos/{repo}/actions/runs"
    params = {}
    if status:
        params["status"] = status
    if branch:
        params["branch"] = branch
    return paginate(token, path, params, max_items)


def actions_get_run(token: str, repo: str, run_id: int):
    return api_request(token, "GET", f"/repos/{repo}/actions/runs/{run_id}")


def actions_rerun(token: str, repo: str, run_id: int):
    return api_request(token, "POST", f"/repos/{repo}/actions/runs/{run_id}/rerun")


def actions_cancel(token: str, repo: str, run_id: int):
    return api_request(token, "POST", f"/repos/{repo}/actions/runs/{run_id}/cancel")


def actions_run_workflow(token: str, repo: str, workflow_id: str, ref: str = "main", inputs: dict | None = None):
    data = {"ref": ref}
    if inputs:
        data["inputs"] = inputs
    return api_request(token, "POST", f"/repos/{repo}/actions/workflows/{workflow_id}/dispatches", data)


# -- Search --------------------------------------------------------------------

def search_repos(token: str, query: str, max_items: int = 30):
    return paginate(token, "/search/repositories", {"q": query}, max_items)


def search_issues(token: str, query: str, max_items: int = 30):
    return paginate(token, "/search/issues", {"q": query}, max_items)


def search_code(token: str, query: str, max_items: int = 30):
    return paginate(token, "/search/code", {"q": query}, max_items)


# -- Gists ---------------------------------------------------------------------

def gist_list(token: str, max_items: int = 30):
    return paginate(token, "/gists", max_items=max_items)


def gist_get(token: str, gist_id: str):
    return api_request(token, "GET", f"/gists/{gist_id}")


def gist_create(token: str, description: str, files: dict, public: bool = False):
    data = {"description": description, "public": public, "files": files}
    return api_request(token, "POST", "/gists", data)


# -- Notifications -------------------------------------------------------------

def notifications_list(token: str, unread: bool = False, max_items: int = 30):
    params = {}
    if unread:
        params["all"] = "false"
    return paginate(token, "/notifications", params, max_items)


# -- CLI -----------------------------------------------------------------------

def output(data):
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="GitHub REST API CLI")
    sub = parser.add_subparsers(dest="command")

    # auth
    sub.add_parser("auth", help="Verify token")

    # repo
    repo_p = sub.add_parser("repo")
    repo_sub = repo_p.add_subparsers(dest="repo_cmd")

    p = repo_sub.add_parser("get")
    p.add_argument("repo")

    p = repo_sub.add_parser("list-branches")
    p.add_argument("repo")
    p.add_argument("--max", type=int, default=30)

    p = repo_sub.add_parser("list-tags")
    p.add_argument("repo")
    p.add_argument("--max", type=int, default=30)

    # issue
    issue_p = sub.add_parser("issue")
    issue_sub = issue_p.add_subparsers(dest="issue_cmd")

    p = issue_sub.add_parser("list")
    p.add_argument("repo")
    p.add_argument("--state", default="open")
    p.add_argument("--labels", default="")
    p.add_argument("--assignee", default="")
    p.add_argument("--max", type=int, default=30)

    p = issue_sub.add_parser("get")
    p.add_argument("repo")
    p.add_argument("number", type=int)

    p = issue_sub.add_parser("create")
    p.add_argument("repo")
    p.add_argument("--title", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--labels", nargs="*", default=None)
    p.add_argument("--assignees", nargs="*", default=None)

    p = issue_sub.add_parser("update")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--title", default=None)
    p.add_argument("--body", default=None)
    p.add_argument("--state", default=None)
    p.add_argument("--labels", nargs="*", default=None)
    p.add_argument("--assignees", nargs="*", default=None)

    p = issue_sub.add_parser("comment")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("body")

    p = issue_sub.add_parser("list-comments")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--max", type=int, default=30)

    # pr
    pr_p = sub.add_parser("pr")
    pr_sub = pr_p.add_subparsers(dest="pr_cmd")

    p = pr_sub.add_parser("list")
    p.add_argument("repo")
    p.add_argument("--state", default="open")
    p.add_argument("--base", default="")
    p.add_argument("--head", default="")
    p.add_argument("--max", type=int, default=30)

    p = pr_sub.add_parser("get")
    p.add_argument("repo")
    p.add_argument("number", type=int)

    p = pr_sub.add_parser("create")
    p.add_argument("repo")
    p.add_argument("--title", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--draft", action="store_true")

    p = pr_sub.add_parser("update")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--title", default=None)
    p.add_argument("--body", default=None)
    p.add_argument("--state", default=None)
    p.add_argument("--base", default=None)

    p = pr_sub.add_parser("merge")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--method", default="merge", choices=["merge", "squash", "rebase"])
    p.add_argument("--commit-title", default="")
    p.add_argument("--commit-message", default="")

    p = pr_sub.add_parser("diff")
    p.add_argument("repo")
    p.add_argument("number", type=int)

    p = pr_sub.add_parser("files")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--max", type=int, default=100)

    p = pr_sub.add_parser("comment")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("body")

    p = pr_sub.add_parser("list-comments")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--max", type=int, default=30)

    p = pr_sub.add_parser("reviews")
    p.add_argument("repo")
    p.add_argument("number", type=int)
    p.add_argument("--max", type=int, default=30)

    p = pr_sub.add_parser("checks")
    p.add_argument("repo")
    p.add_argument("number", type=int)

    # release
    rel_p = sub.add_parser("release")
    rel_sub = rel_p.add_subparsers(dest="rel_cmd")

    p = rel_sub.add_parser("list")
    p.add_argument("repo")
    p.add_argument("--max", type=int, default=30)

    p = rel_sub.add_parser("get")
    p.add_argument("repo")
    p.add_argument("tag")

    p = rel_sub.add_parser("latest")
    p.add_argument("repo")

    p = rel_sub.add_parser("create")
    p.add_argument("repo")
    p.add_argument("--tag", required=True)
    p.add_argument("--name", default="")
    p.add_argument("--body", default="")
    p.add_argument("--draft", action="store_true")
    p.add_argument("--prerelease", action="store_true")
    p.add_argument("--target", default="")

    # actions
    act_p = sub.add_parser("actions")
    act_sub = act_p.add_subparsers(dest="act_cmd")

    p = act_sub.add_parser("workflows")
    p.add_argument("repo")

    p = act_sub.add_parser("runs")
    p.add_argument("repo")
    p.add_argument("--workflow", default="")
    p.add_argument("--status", default="")
    p.add_argument("--branch", default="")
    p.add_argument("--max", type=int, default=20)

    p = act_sub.add_parser("get-run")
    p.add_argument("repo")
    p.add_argument("run_id", type=int)

    p = act_sub.add_parser("rerun")
    p.add_argument("repo")
    p.add_argument("run_id", type=int)

    p = act_sub.add_parser("cancel")
    p.add_argument("repo")
    p.add_argument("run_id", type=int)

    p = act_sub.add_parser("run-workflow")
    p.add_argument("repo")
    p.add_argument("workflow_id")
    p.add_argument("--ref", default="main")
    p.add_argument("--inputs", default=None, help="JSON string of inputs")

    # search
    search_p = sub.add_parser("search")
    search_sub = search_p.add_subparsers(dest="search_cmd")

    p = search_sub.add_parser("repos")
    p.add_argument("query")
    p.add_argument("--max", type=int, default=30)

    p = search_sub.add_parser("issues")
    p.add_argument("query")
    p.add_argument("--max", type=int, default=30)

    p = search_sub.add_parser("code")
    p.add_argument("query")
    p.add_argument("--max", type=int, default=30)

    # gist
    gist_p = sub.add_parser("gist")
    gist_sub = gist_p.add_subparsers(dest="gist_cmd")

    p = gist_sub.add_parser("list")
    p.add_argument("--max", type=int, default=30)

    p = gist_sub.add_parser("get")
    p.add_argument("gist_id")

    p = gist_sub.add_parser("create")
    p.add_argument("--description", default="")
    p.add_argument("--public", action="store_true")
    p.add_argument("files", nargs="+", help="filename=content pairs")

    # notifications
    p = sub.add_parser("notifications")
    p.add_argument("--unread", action="store_true")
    p.add_argument("--max", type=int, default=30)

    args = parser.parse_args()
    token = load_token()

    if args.command == "auth":
        output(cmd_auth(token))

    elif args.command == "repo":
        cmd = args.repo_cmd
        if cmd == "get":
            output(repo_get(token, args.repo))
        elif cmd == "list-branches":
            output(repo_list_branches(token, args.repo, args.max))
        elif cmd == "list-tags":
            output(repo_list_tags(token, args.repo, args.max))

    elif args.command == "issue":
        cmd = args.issue_cmd
        if cmd == "list":
            output(issue_list(token, args.repo, args.state, args.labels, args.assignee, args.max))
        elif cmd == "get":
            output(issue_get(token, args.repo, args.number))
        elif cmd == "create":
            output(issue_create(token, args.repo, args.title, args.body, args.labels, args.assignees))
        elif cmd == "update":
            output(issue_update(token, args.repo, args.number, args.title, args.body,
                                args.state, args.labels, args.assignees))
        elif cmd == "comment":
            output(issue_comment(token, args.repo, args.number, args.body))
        elif cmd == "list-comments":
            output(issue_list_comments(token, args.repo, args.number, args.max))

    elif args.command == "pr":
        cmd = args.pr_cmd
        if cmd == "list":
            output(pr_list(token, args.repo, args.state, args.base, args.head, args.max))
        elif cmd == "get":
            output(pr_get(token, args.repo, args.number))
        elif cmd == "create":
            output(pr_create(token, args.repo, args.title, args.head, args.base, args.body, args.draft))
        elif cmd == "update":
            output(pr_update(token, args.repo, args.number, args.title, args.body, args.state, args.base))
        elif cmd == "merge":
            output(pr_merge(token, args.repo, args.number, args.method, args.commit_title, args.commit_message))
        elif cmd == "diff":
            output(pr_diff(token, args.repo, args.number))
        elif cmd == "files":
            output(pr_files(token, args.repo, args.number, args.max))
        elif cmd == "comment":
            output(pr_comment(token, args.repo, args.number, args.body))
        elif cmd == "list-comments":
            output(pr_list_comments(token, args.repo, args.number, args.max))
        elif cmd == "reviews":
            output(pr_reviews(token, args.repo, args.number, args.max))
        elif cmd == "checks":
            output(pr_checks(token, args.repo, args.number))

    elif args.command == "release":
        cmd = args.rel_cmd
        if cmd == "list":
            output(release_list(token, args.repo, args.max))
        elif cmd == "get":
            output(release_get(token, args.repo, args.tag))
        elif cmd == "latest":
            output(release_latest(token, args.repo))
        elif cmd == "create":
            output(release_create(token, args.repo, args.tag, args.name, args.body,
                                  args.draft, args.prerelease, args.target))

    elif args.command == "actions":
        cmd = args.act_cmd
        if cmd == "workflows":
            output(actions_workflows(token, args.repo))
        elif cmd == "runs":
            output(actions_runs(token, args.repo, args.workflow, args.status, args.branch, args.max))
        elif cmd == "get-run":
            output(actions_get_run(token, args.repo, args.run_id))
        elif cmd == "rerun":
            output(actions_rerun(token, args.repo, args.run_id))
        elif cmd == "cancel":
            output(actions_cancel(token, args.repo, args.run_id))
        elif cmd == "run-workflow":
            inputs = json.loads(args.inputs) if args.inputs else None
            output(actions_run_workflow(token, args.repo, args.workflow_id, args.ref, inputs))

    elif args.command == "search":
        cmd = args.search_cmd
        if cmd == "repos":
            output(search_repos(token, args.query, args.max))
        elif cmd == "issues":
            output(search_issues(token, args.query, args.max))
        elif cmd == "code":
            output(search_code(token, args.query, args.max))

    elif args.command == "gist":
        cmd = args.gist_cmd
        if cmd == "list":
            output(gist_list(token, args.max))
        elif cmd == "get":
            output(gist_get(token, args.gist_id))
        elif cmd == "create":
            files = {}
            for f in args.files:
                name, content = f.split("=", 1)
                files[name] = {"content": content}
            output(gist_create(token, args.description, files, args.public))

    elif args.command == "notifications":
        output(notifications_list(token, args.unread, args.max))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
