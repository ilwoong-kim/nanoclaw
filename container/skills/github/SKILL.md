---
name: github
description: >
  GitHub REST API integration for repositories, issues, pull requests, releases,
  actions, search, gists, and notifications.
  Use when tasks involve: (1) GitHub issues — creating, updating, commenting, searching;
  (2) Pull requests — creating, reviewing, merging, checking CI status;
  (3) Releases — listing, creating; (4) Actions — viewing workflow runs, re-running;
  (5) Code search — finding code across repositories; (6) Repository info — branches, tags.
  Triggers: "github", "깃허브", "issue", "이슈", "pull request", "PR", "merge",
  "release", "릴리즈", "actions", "workflow", "CI", "gist", "repo", "repository".
---

# GitHub REST API

## When to Use This Skill

Use this skill's Python script for all GitHub operations. Web browsing may fail due to authentication requirements.

### Explicit triggers
User mentions GitHub, repo, issue, PR, pull request, merge, release, actions, workflow, CI, gist, 깃허브, 이슈, 릴리즈

### Deep Code Exploration

GitHub API는 이슈, PR, Actions, commit history 등 메타데이터 조회에 최적화되어 있다.
코드 아키텍처 분석, 구현 추적, 파일 간 패턴 검색 등 **깊은 코드 탐색**이 필요하면
로컬에 clone된 레포를 직접 탐색하라. `/workspace/extra/repos/` 참조.

## Credentials

`GITHUB_TOKEN` is injected via environment variable by the host. No setup needed inside the container.

Required token scopes (classic PAT): `repo`, `workflow`, `gist`, `notifications`, `read:org`

## Script Location

```bash
SCRIPT="/home/node/.claude/skills/github/scripts/github_api.py"
```

## Quick Reference

### Auth Check

```bash
python3 $SCRIPT auth
```

### Repos

```bash
python3 $SCRIPT repo get owner/repo
python3 $SCRIPT repo list-branches owner/repo
python3 $SCRIPT repo list-tags owner/repo
```

### Issues

```bash
# List open issues
python3 $SCRIPT issue list owner/repo
python3 $SCRIPT issue list owner/repo --state closed --labels "bug,urgent"
python3 $SCRIPT issue list owner/repo --assignee username

# Get single issue
python3 $SCRIPT issue get owner/repo 123

# Create issue
python3 $SCRIPT issue create owner/repo --title "Bug report" --body "Details here"
python3 $SCRIPT issue create owner/repo --title "Task" --labels bug enhancement --assignees user1

# Update / close
python3 $SCRIPT issue update owner/repo 123 --state closed
python3 $SCRIPT issue update owner/repo 123 --title "New title" --labels bug

# Comments
python3 $SCRIPT issue comment owner/repo 123 "comment text"
python3 $SCRIPT issue list-comments owner/repo 123
```

### Pull Requests

```bash
# List PRs
python3 $SCRIPT pr list owner/repo
python3 $SCRIPT pr list owner/repo --state all --base main

# Get single PR
python3 $SCRIPT pr get owner/repo 123

# Create PR
python3 $SCRIPT pr create owner/repo --title "Feature" --head feature-branch --base main --body "Description"
python3 $SCRIPT pr create owner/repo --title "WIP" --head dev --base main --draft

# Update
python3 $SCRIPT pr update owner/repo 123 --title "Updated title"

# Merge
python3 $SCRIPT pr merge owner/repo 123 --method squash
python3 $SCRIPT pr merge owner/repo 123 --method rebase

# Diff and files
python3 $SCRIPT pr diff owner/repo 123
python3 $SCRIPT pr files owner/repo 123

# Comments
python3 $SCRIPT pr comment owner/repo 123 "LGTM"
python3 $SCRIPT pr list-comments owner/repo 123

# Reviews and CI checks
python3 $SCRIPT pr reviews owner/repo 123
python3 $SCRIPT pr checks owner/repo 123
```

### Releases

```bash
python3 $SCRIPT release list owner/repo
python3 $SCRIPT release latest owner/repo
python3 $SCRIPT release get owner/repo v1.0.0
python3 $SCRIPT release create owner/repo --tag v1.0.0 --name "Release 1.0" --body "Release notes"
```

### Actions / Workflows

```bash
# List workflows
python3 $SCRIPT actions workflows owner/repo

# List runs
python3 $SCRIPT actions runs owner/repo
python3 $SCRIPT actions runs owner/repo --workflow build.yml --status failure --branch main

# Get specific run
python3 $SCRIPT actions get-run owner/repo 123456

# Re-run / cancel
python3 $SCRIPT actions rerun owner/repo 123456
python3 $SCRIPT actions cancel owner/repo 123456

# Trigger workflow manually
python3 $SCRIPT actions run-workflow owner/repo deploy.yml --ref main --inputs '{"env":"prod"}'
```

### Search

```bash
# Search repos
python3 $SCRIPT search repos "nanoclaw language:typescript"

# Search issues/PRs
python3 $SCRIPT search issues "repo:owner/repo is:open label:bug"

# Search code
python3 $SCRIPT search code "repo:owner/repo filename:config.ts api_key"
```

### Gists

```bash
python3 $SCRIPT gist list
python3 $SCRIPT gist get abc123def
python3 $SCRIPT gist create --description "My snippet" snippet.py="print('hello')"
python3 $SCRIPT gist create --public notes.md="# Notes"
```

### Notifications

```bash
python3 $SCRIPT notifications
python3 $SCRIPT notifications --unread
```

## Direct API Calls (Python)

For operations not covered by the CLI:

```python
import sys
sys.path.insert(0, "/home/node/.claude/skills/github/scripts")
from github_api import load_token, api_request

token = load_token()

# Any endpoint
result = api_request(token, "GET", "/repos/owner/repo")
result = api_request(token, "POST", "/repos/owner/repo/issues", body={"title": "New issue"})
```

## Default Organization

**Quantit-Github** — 명시적으로 다른 owner를 지정하지 않으면 이 org를 기본으로 사용.

### Watched Repositories

#### Platform & Infra

| Repo | Purpose | Tech |
|------|---------|------|
| `Quantit-Github/arkraft-api` | Arkraft 백엔드 API — 리서치 워크플로우, 알파 풀, 디스커버리 세션 관리 | FastAPI, SQLAlchemy 2.0, Celery, PostgreSQL, Redis, Cognito JWT |
| `Quantit-Github/arkraft-web` | Arkraft 프론트엔드 웹 애플리케이션 | — |
| `Quantit-Github/arkraft-wiki` | Arkraft 제품 위키 — 서비스 비전, 철학, 온톨로지, 아키텍처 등 최상위 추상화 문서 (높은 중요도) | — |
| `Quantit-Github/arkraft-deploy` | K8s 배포 — Helm charts + ArgoCD (web/api/agents) | Helm, ArgoCD, Istio, AWS ALB |
| `Quantit-Github/ai-infra` | AI 인프라 IaC — VPC, EKS, ArgoCD, Argo Workflows, Monitoring | Terraform, Atlantis, kube-prometheus-stack |

#### Agents (Claude Agent SDK 기반)

| Repo | Purpose | Key Detail |
|------|---------|------------|
| `Quantit-Github/arkraft-agent-alpha` | 퀀트 알파 리서치 — 4-agent 협업 (PM → DE → DA → QD), 6-phase 워크플로우 | Design → Prep → Explore → Review → Implement → Eval |
| `Quantit-Github/arkraft-agent-insight` | 알파풀 분석 + 리서치 가설 생성 — 7-phase (PARSE → IDEATE → SEARCH → JUDGE → EXECUTE → SAVE → VALIDATE) | Universe: kr/us/vn/id stock, us_etf, btcusdt |
| `Quantit-Github/arkraft-agent-portfolio` | 포트폴리오 관리 및 최적화 | — |
| `Quantit-Github/arkraft-agent-extract` | PDF/DOCX → 구조화된 마크다운 리포트 추출 (arkraft-agent-distilling 후속) | S3 input/output, YAML frontmatter + MD |
| `Quantit-Github/arkraft-agent-data` | CSV/외부DB → CM 데이터 카탈로그 등록 파이프라인 (5단계 CSV + 4단계 DB) | detect-normalize → cm-check → spec → transform → register |
| `Quantit-Github/arkraft-agent-report` | 금융 리포트 자동 생성 — 6-phase 멀티 에이전트 (planner → data → reasoning → report → HTML → quality) | S3 업로드, RabbitMQ lifecycle, Redis SSE |

### Common Examples with Default Repos

```bash
# arkraft-api 최근 PR 확인
python3 $SCRIPT pr list Quantit-Github/arkraft-api

# arkraft-agent-alpha 이슈 검색
python3 $SCRIPT issue list Quantit-Github/arkraft-agent-alpha --state open

# ai-infra 최근 Actions 실행 확인
python3 $SCRIPT actions runs Quantit-Github/ai-infra

# org 전체에서 코드 검색
python3 $SCRIPT search code "org:Quantit-Github filename:CLAUDE.md"

# org 전체 이슈 검색
python3 $SCRIPT search issues "org:Quantit-Github is:open label:bug"
```

## Key Conventions

- All repo arguments use `owner/repo` format (e.g., `Quantit-Github/arkraft-api`)
- Issue/PR numbers are integers, not prefixed with `#`
- Search queries follow [GitHub search syntax](https://docs.github.com/en/search-github/searching-on-github)
- PR comments use the issues API (GitHub treats PR comments as issue comments)
- `--max` flag controls pagination limit (default varies by command)
- JSON output is always pretty-printed
