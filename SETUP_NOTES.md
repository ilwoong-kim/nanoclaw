# NanoClaw Setup Notes

설치 완료: 2026-04-09

## 구성

| 항목 | 값 |
|---|---|
| Platform | macOS (Darwin x86_64) |
| Node | 22.22.2 |
| Container runtime | Docker |
| Credential system | OneCLI (http://127.0.0.1:10254) |
| Anthropic auth | Claude Pro/Max OAuth token (OneCLI secret name: `Anthropic`) |
| Timezone | Asia/Seoul |
| Assistant name | Luffy-Bot (`.env` `ASSISTANT_NAME`) |
| Service | launchd (`com.nanoclaw`) |

## 채널

### Telegram
- Bot: `@luffy_qt_bot` (token in `.env` `TELEGRAM_BOT_TOKEN`)
- 등록된 채팅: `tg:8749056951` (Luffy, 1:1 DM)
- Group folder: `groups/telegram_main/`
- Mode: **main** — 트리거 없이 모든 메시지에 응답

### Slack
- App: workspace에 설치된 Slack 앱 (Socket Mode)
- Bot/App tokens in `.env` (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`)
- 등록된 채널: `slack:C08E8QTPQP9`
- Group folder: `groups/slack_main_channel/`
- Mode: **트리거 필요** — Slack에서 봇을 `@luffy-bot`으로 멘션. Slack 채널 코드가 멘션을 어시스턴트 트리거(`@Luffy-Bot`)로 정규화해서 NanoClaw에 전달
- 알려진 제약: 스레드에서 메시지를 받아도 답변은 메인 채널에 올라감 (스레드 인식 미지원)

## 격리 (중요)

각 그룹은 완전히 분리된 메모리/파일시스템을 가짐:
- Telegram 에이전트와 Slack 에이전트는 **서로의 대화를 모름**
- 공유 정보가 필요하면 `groups/global/CLAUDE.md`에 적음
- 그룹별 지시사항/메모는 `groups/<name>/CLAUDE.md`에 적음

### Obsidian
- Local REST API plugin in Obsidian Desktop (HTTPS 27124, self-signed)
- Vault: `~/Documents/ObsidianVault/luffy`
- API key in `.env` `OBSIDIAN_API_KEY`, base url in `OBSIDIAN_BASE_URL`
- Container has `obsidian-mcp-server` preinstalled, exposes `mcp__obsidian__*` tools to the agent
- Two gotchas baked into the integration (see `.claude/skills/add-obsidian/SKILL.md`):
  - logs dir under `/usr/local/lib/node_modules/obsidian-mcp-server/logs` is pre-chmodded 1777 in the Dockerfile (otherwise the server silently `process.exit(1)`s)
  - `NO_PROXY=host.docker.internal,127.0.0.1,localhost` is forced into the obsidian MCP env so axios bypasses the OneCLI proxy (otherwise the status check returns 400)

## Mount allowlist

빈 상태(`/Users/luffy/.config/nanoclaw/mount-allowlist.json`).
컨테이너는 자기 그룹 폴더만 볼 수 있음. 외부 경로 추가하려면 그 파일 수정 후 서비스 재시작.

Slack에서 자동 등록되는 그룹에 기본 마운트를 일괄 적용하려면 `.env`의 `SLACK_DEFAULT_ADDITIONAL_MOUNTS`에 JSON 배열을 넣는다 (예: quantit-repo 마운트). 시작 시 기존 Slack 그룹은 `additionalMounts`가 비어 있으면 backfill되고, 신규 Slack 자동등록에도 기본값으로 들어간다.

## 자주 쓰는 명령

```bash
# 로그 보기
tail -f logs/nanoclaw.log

# 서비스 제어
launchctl kickstart -k gui/$(id -u)/com.nanoclaw   # 재시작
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist  # 정지
launchctl load ~/Library/LaunchAgents/com.nanoclaw.plist    # 시작

# Dev 모드 (서비스 정지 후)
npm run dev

# 빌드
npm run build

# 컨테이너 이미지 재빌드
./container/build.sh

# OneCLI 시크릿 확인
onecli secrets list

# 등록된 그룹 확인
sqlite3 store/messages.db "SELECT jid, name, folder, requires_trigger FROM registered_groups"
```

## 채널 추가/제거 시

- 새 채널: `/customize` 또는 `/add-<channel>` 스킬
- 업데이트 가져오기: `/update-nanoclaw`
- 문제 진단: `/debug`
