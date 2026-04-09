# Weekly Note Format

## Frontmatter

```yaml
---
week: "2026-WNN"
period: "YYYY-MM-DD ~ YYYY-MM-DD"
projects: [arkraft, alpha-pool, ...]
people: [재현, 낙훈, 동현, ...]
my_issues: [ARK-1234, ARK-1235, ...]
highlights: [핵심 이벤트 1, 핵심 이벤트 2, ...]
tags: [topic-tag-1, topic-tag-2, ...]
---
```

### Field Rules

| Field | Content |
|-------|---------|
| `week` | ISO week format: `2026-W15` |
| `period` | Monday ~ Sunday: `2026-04-07 ~ 2026-04-13` |
| `projects` | Lowercase project names detected from data |
| `people` | Korean first names only, people I interacted with |
| `my_issues` | Jira issue keys I was assigned to or worked on |
| `highlights` | 3~6 key events, Korean, concise |
| `tags` | Lowercase topic tags (e.g., `metering`, `staging`, `data-integration`) |

## Body Structure

```markdown
# YYYY-WNN (Mon DD - Day DD, YYYY) — 한 줄 요약 제목

## 나의 활동

### 업무
- **ARK-XXXX** 이슈 제목 — 상태/진행률
  - 세부사항 (PR 번호, 기술적 내용)
  - 관련 대화/결정

### 기타
- 재택/출근 패턴
- 팀 외 활동 (회식, 마라톤 등)

## 나를 멘션한 것
- **이름** (채널): 멘션 내용 요약

## 팀 주요 업데이트

### 토픽별 소제목 — 가장 중요한 것 먼저
- 내용

### Slack — channel_name
- 내용 (project_ark에 해당하지 않는 채널별 정리)

### Confluence — ARK (N페이지)
- 페이지 제목: 핵심 내용 1줄

### Confluence — QW (N페이지)
- (있으면)

### Jira — ARK (N건)
- **내 이슈 N건**: 이슈 키, 제목, 상태
- **팀원별**: 핵심 작업 요약

### GitHub
- **내 PR N건**: 주요 PR 제목
- **repo별**: 전체 PR 수 + 핵심 주제

## 주간 인사이트
- **볼드 키워드**: 이번 주에서 가장 중요한 시사점 3~5개
```

## Writing Guidelines

1. **나의 활동이 가장 중요** — 가장 상세하게 작성
2. **팀 업데이트는 토픽 중심** — 채널별이 아니라 주제별로 그룹핑
3. **인사이트는 맥락 제공** — 단순 사실 나열이 아닌 "왜 중요한지" 포함
4. **분량**: 80~150줄 목표. 바쁜 주는 길어질 수 있음
5. **빠진 것 보다 중복이 나음** — daily에 있었지만 weekly에서 빠지면 안됨
