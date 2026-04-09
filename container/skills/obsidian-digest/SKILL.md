---
name: obsidian-digest
description: >
  Automated work context digest — collects Slack, Jira, GitHub data and writes
  structured summaries to Obsidian vault. Two modes: daily (Mon-Sat lightweight)
  and weekly (Sun comprehensive synthesis).
  Triggers: "daily digest", "weekly digest", "일간 요약", "주간 요약",
  "오늘 정리", "이번주 정리", "digest", "work summary".
---

# Obsidian Work Digest

Collects work context from Slack, Jira, GitHub and writes structured summaries to the Obsidian vault.

## Modes

| Mode | When | Output | Scope |
|------|------|--------|-------|
| **daily** | Mon-Sat 18:00 KST | `daily/YYYY-MM-DD.md` | Lightweight — Slack 2ch + mentions + Jira + arkraft-wiki |
| **weekly** | Sun 09:00 KST | `weekly/YYYY-WNN.md` | Comprehensive — Slack 5ch + Confluence + full Jira + GitHub 3 repos. Deletes daily files after. |

## Owner Identity

| Field | Value |
|-------|-------|
| Name | 김일웅 (ilwoong.kim) |
| Slack User ID | `U01QGDBGJRF` |
| Atlassian Account ID | `6040590ac58c72007140a156` |
| GitHub Username | `ilwoong-kim` |

## Script Locations

```bash
SLACK="/home/node/.claude/skills/slack-reader/scripts"
ATLAS="/home/node/.claude/skills/atlassian/scripts/atlassian_api.py"
GITHUB="/home/node/.claude/skills/github/scripts/github_api.py"
```

## Obsidian Vault — Direct File Write

The vault is mounted at `/workspace/extra/vault` inside the container. Write files directly to this path.
**Do NOT use Obsidian MCP tools** — they depend on a flaky REST API plugin.

```bash
VAULT="/workspace/extra/vault"  # host: /Users/luffy/Documents/ObsidianVault/luffy
# daily note:  $VAULT/daily/2026-04-09.md
# weekly note: $VAULT/weekly/2026-W15.md
```

Create directories if they don't exist: `mkdir -p $VAULT/daily $VAULT/weekly`

---

## Mode 1: Daily Digest

Run on **Mon-Sat**. Collect today's data and write a lightweight summary.

### Step 1: Determine Date Range

```
TODAY = current date (YYYY-MM-DD)
TOMORROW = TODAY + 1 day
# Convert to Unix timestamps for Slack (KST 00:00 of each day)
```

### Step 2: Collect Data (parallel where possible)

**Slack — 2 channels + 2 searches:**

```bash
# amt_team
python3 $SLACK/read_history.py C0891E6DDPA --threads --limit 200 --oldest $TODAY_TS --latest $TOMORROW_TS

# project_ark
python3 $SLACK/read_history.py C0933M2A5CK --threads --limit 200 --oldest $TODAY_TS --latest $TOMORROW_TS

# Messages I sent
python3 $SLACK/search_messages.py "from:<@U01QGDBGJRF> after:$TODAY before:$TOMORROW" --count 50 --json

# Messages mentioning me
python3 $SLACK/search_messages.py "to:<@U01QGDBGJRF> after:$TODAY before:$TOMORROW" --count 50 --json
```

**Jira — ARK project updated today:**

```bash
python3 $ATLAS jira search 'project = ARK AND updated >= "$TODAY" AND updated < "$TOMORROW" ORDER BY updated DESC'
```

**GitHub — arkraft-wiki PRs only:**

```bash
python3 $GITHUB pr list Quantit-Github/arkraft-wiki --state all --json
# Filter to PRs created or updated today
```

### Step 3: Write Daily Note

Write directly to: `$VAULT/daily/$TODAY.md`

**Format:**

```markdown
---
date: "YYYY-MM-DD"
projects: [detected from data]
people: [names mentioned/interacted]
tags: [topic tags]
---

# YYYY-MM-DD (Day)

## 나
- [My activities — from sent messages, Jira updates I'm assigned to]

## 멘션
- [Messages that mentioned me — who, what channel, what about]

## 팀
- [Key team events from amt_team and project_ark — decisions, deployments, issues]

## Jira
- [Issues updated today — key, summary, status, assignee — focus on my issues first]
```

**Guidelines:**
- Keep it short — 15~30 lines max for the body
- Korean for content, English for technical terms
- Group by topic, not by data source
- Skip bot messages, reminders, routine syncs
- If nothing meaningful happened, write "특이사항 없음" under each section

---

## Mode 2: Weekly Digest

Run on **Sunday**. Read the 6 daily files, supplement with additional sources, write comprehensive weekly summary, then delete dailies.

### Step 1: Determine Week Range

```
WEEK_START = Monday of this week (YYYY-MM-DD)
WEEK_END = Saturday of this week (YYYY-MM-DD)
WEEK_END_PLUS1 = Sunday (for query ranges)
ISO_WEEK = YYYY-WNN format
```

### Step 2: Read Daily Files

Read all existing daily files for this week from `$VAULT/daily/`:

```bash
ls $VAULT/daily/  # Mon through Sat files for this week
cat $VAULT/daily/YYYY-MM-DD.md  # Read each one
```

These provide the skeleton. The following steps fill gaps.

### Step 3: Collect Supplementary Data

**Slack — 3 additional channels (amt_team and project_ark already covered by dailies):**

```bash
# ark_team
python3 $SLACK/read_history.py C08E8QTPQP9 --threads --limit 200 --oldest $WEEK_START_TS --latest $WEEK_END_PLUS1_TS

# 기술연구소
python3 $SLACK/read_history.py C0233GCAK6V --threads --limit 200 --oldest $WEEK_START_TS --latest $WEEK_END_PLUS1_TS

# project_finter
python3 $SLACK/read_history.py C03HKQ8AJ8Z --threads --limit 200 --oldest $WEEK_START_TS --latest $WEEK_END_PLUS1_TS
```

**Confluence:**

```bash
python3 $ATLAS confluence search 'type = page AND space = "ARK" AND lastModified >= "$WEEK_START" AND lastModified < "$WEEK_END_PLUS1"'
python3 $ATLAS confluence search 'type = page AND space = "QW" AND lastModified >= "$WEEK_START" AND lastModified < "$WEEK_END_PLUS1"'
```

**Jira — full week (dailies only have individual days):**

```bash
python3 $ATLAS jira search 'project = ARK AND updated >= "$WEEK_START" AND updated < "$WEEK_END_PLUS1" ORDER BY updated DESC'
python3 $ATLAS jira search 'project = ARK AND assignee = "6040590ac58c72007140a156" AND updated >= "$WEEK_START" AND updated < "$WEEK_END_PLUS1" ORDER BY updated DESC'
```

**GitHub — 3 repos + my PRs:**

```bash
# Team PRs (filter by date range in output)
python3 $GITHUB pr list Quantit-Github/arkraft-api --state all --json
python3 $GITHUB pr list Quantit-Github/arkraft-web --state all --json
python3 $GITHUB pr list Quantit-Github/arkraft-wiki --state all --json

# My PRs across all repos
# Use: gh search prs --author=ilwoong-kim --created=$WEEK_START..$WEEK_END
```

### Step 4: Write Weekly Note

Write directly to: `$VAULT/weekly/$ISO_WEEK.md`

Use the format documented in `references/weekly-format.md`.

### Step 5: Delete Daily Files

After the weekly note is successfully written, delete all daily files for this week:

```bash
rm $VAULT/daily/YYYY-MM-DD.md  # each day Mon through Sat
```

---

## Slack Channel IDs

| Channel | ID | Daily | Weekly |
|---------|-----|-------|--------|
| amt_team | `C0891E6DDPA` | ✓ | (from daily) |
| project_ark | `C0933M2A5CK` | ✓ | (from daily) |
| ark_team | `C08E8QTPQP9` | | ✓ |
| 기술연구소 | `C0233GCAK6V` | | ✓ |
| project_finter | `C03HKQ8AJ8Z` | | ✓ |

## Tier System

- **Tier 1 (상세)** — 나를 멘션한 것, 내가 쓴 것, 내 PR/이슈
- **Tier 2 (요약)** — 팀 채널 주요 공지/결정, @amt 멘션
- **Tier 3 (한 줄)** — 회사 전체 공지, 기술연구소 동향

## Frontmatter — projects Field

Use **project names**, not repo names. Repos like arkraft-api, arkraft-web, arkraft-wiki, arkraft-deploy, ai-infra all belong to `arkraft`.

| Project Name | Includes |
|-------------|----------|
| `arkraft` | arkraft-api, arkraft-web, arkraft-wiki, arkraft-deploy, arkraft-agent-*, arkraft-sdk, ai-infra |
| `alpha-pool` | alpha-pool-infra |
| `signal-finder` | signal finder 관련 작업 |
| `moneytoring` | ark-moneytoring-agent, DIP 관련 |
| `finter` | finter, finterlabs, c2api 관련 |
| `distilling` | arkraft-agent-distilling, arkraft-agent-extract |

## Frontmatter — people Field

이름만 적고 "님" 접미사는 생략: `재현`, `동현` (not `재현님`, `동현님`)

## Key Conventions

- Korean for content, English for technical terms
- Skip bot messages (USLACKBOT, B0493CDTL0M etc.) and routine reminders
- People names: 이름만 (e.g., 재현님, 동현님) — no full names or IDs in body
- Jira issue keys as-is (e.g., ARK-1234)
- GitHub PR references: repo#number (e.g., arkraft-api #500)
- Dates in ISO format (YYYY-MM-DD)
- If a section has no content, omit the section entirely rather than writing "없음"
