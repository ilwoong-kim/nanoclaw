---
name: add-obsidian
description: Connect NanoClaw container agents to a local Obsidian vault via the Local REST API plugin and the obsidian-mcp-server MCP. Use this skill whenever the user wants their NanoClaw assistant to read, write, search, or manage notes in their Obsidian vault — including phrases like "obsidian", "옵시디언", "vault에 노트 추가", "second brain", "내 노트 검색해줘".
type: feature
---

# Add Obsidian to NanoClaw

This skill makes the NanoClaw container agent able to talk to a local Obsidian vault using the **Local REST API** community plugin (in Obsidian) plus the **obsidian-mcp-server** npm package (in the agent container). All requests stay on the host machine — nothing is sent to Obsidian's cloud.

## Architecture

```
Telegram/Slack message
        ↓
NanoClaw orchestrator (host)
        ↓ docker run -e OBSIDIAN_API_KEY=... -e NO_PROXY=...
Agent container
        ↓ Claude SDK → claude binary → spawns mcp__obsidian
obsidian-mcp-server (stdio MCP)
        ↓ axios HTTPS
host.docker.internal:27124
        ↓
Obsidian Desktop app (Local REST API plugin)
        ↓
~/Documents/ObsidianVault/<your-vault>/*.md
```

The Obsidian Desktop app must be running for this integration to work.

## Why this is non-obvious (read this before debugging)

Two surprising things bit us when we built this:

1. **The MCP server silently exits if it can't write its log directory.**
   `obsidian-mcp-server` writes Winston logs into `<package_root>/logs/`, which on a `npm install -g` install means `/usr/local/lib/node_modules/obsidian-mcp-server/logs/` — root-owned and not writable by the agent's non-root user. When the directory creation fails the server calls `process.exit(1)` with **no stderr output** because `process.stderr.isTTY === false`. The Claude SDK then registers the MCP server in its config but never receives any tools from it. **Pre-create that directory with world-writable perms in the Dockerfile.**

2. **OneCLI sets `HTTP(S)_PROXY` for everything in the container.**
   The OneCLI gateway intercepts Anthropic API requests by setting `HTTPS_PROXY=host.docker.internal:10255` in the agent container's env. axios (which obsidian-mcp-server uses) automatically follows that env var, so the obsidian status check (`GET https://host.docker.internal:27124/`) gets routed to the OneCLI gateway, which doesn't recognize the destination and returns **400 Bad Request**. curl and node's native `https` module ignore the proxy env vars by default, which is why manual testing always worked. **Pass `NO_PROXY=host.docker.internal,127.0.0.1,localhost` in the obsidian MCP server's env block** so axios bypasses OneCLI for loopback hosts.

If anything regresses around obsidian, check these two first.

## Phase 1: Pre-flight on the host

1. Install Obsidian Desktop from https://obsidian.md (no account needed)
2. Create a vault (any folder)
3. Install the **Local REST API** community plugin in Obsidian:
   - Settings → Community plugins → Browse → "Local REST API" → Install + Enable
   - Open the plugin's settings, copy the **API key**
4. Confirm the API responds (default is HTTPS on 27124 with a self-signed cert):
   ```bash
   curl -ks -H "Authorization: Bearer <YOUR_API_KEY>" https://127.0.0.1:27124/
   ```
   You should get back a JSON blob with `"status": "OK"` and `"authenticated": true`.

## Phase 2: Apply code changes

These four edits make obsidian opt-in based on whether `OBSIDIAN_API_KEY` is present in `.env`. Without the env var, nothing changes — existing setups are unaffected.

### 2a. Dockerfile — install MCP server and pre-create logs dir

In `container/Dockerfile`, change the global npm install line to add `obsidian-mcp-server`, and pre-create its logs dir:

```dockerfile
RUN npm install -g agent-browser @anthropic-ai/claude-code obsidian-mcp-server

# obsidian-mcp-server insists on writing logs inside its own package dir.
# Pre-create with world-writable perms so the non-root agent user can use it.
# Otherwise the server exits silently with code 1 when started by a non-root user.
RUN mkdir -p /usr/local/lib/node_modules/obsidian-mcp-server/logs \
    && chmod 1777 /usr/local/lib/node_modules/obsidian-mcp-server/logs
```

### 2b. `src/container-runner.ts` — forward credentials to the container

Add the import:
```ts
import { readEnvFile } from './env.js';
```

In `buildContainerArgs()`, right after the `TZ` env push, add:
```ts
const obsidianEnv = readEnvFile(['OBSIDIAN_API_KEY', 'OBSIDIAN_BASE_URL']);
if (obsidianEnv.OBSIDIAN_API_KEY) {
  args.push('-e', `OBSIDIAN_API_KEY=${obsidianEnv.OBSIDIAN_API_KEY}`);
  args.push(
    '-e',
    `OBSIDIAN_BASE_URL=${obsidianEnv.OBSIDIAN_BASE_URL || 'https://host.docker.internal:27124'}`,
  );
  args.push('-e', 'OBSIDIAN_VERIFY_SSL=false');
}
```

We use `readEnvFile` (NanoClaw's helper) instead of `process.env` so secrets don't leak into the orchestrator's process environment.

### 2c. `container/agent-runner/src/index.ts` — register the MCP server

Import the type:
```ts
import {
  query,
  HookCallback,
  McpServerConfig,
  PreCompactHookInput,
} from '@anthropic-ai/claude-agent-sdk';
```

Build `mcpServers` dynamically before the `query()` call so optional servers can be added based on env:
```ts
const mcpServers: Record<string, McpServerConfig> = {
  nanoclaw: {
    command: 'node',
    args: [mcpServerPath],
    env: {
      NANOCLAW_CHAT_JID: containerInput.chatJid,
      NANOCLAW_GROUP_FOLDER: containerInput.groupFolder,
      NANOCLAW_IS_MAIN: containerInput.isMain ? '1' : '0',
    },
  },
};

if (process.env.OBSIDIAN_API_KEY) {
  mcpServers.obsidian = {
    command: 'node',
    args: ['/usr/local/lib/node_modules/obsidian-mcp-server/dist/index.js'],
    env: {
      OBSIDIAN_API_KEY: process.env.OBSIDIAN_API_KEY,
      OBSIDIAN_BASE_URL:
        process.env.OBSIDIAN_BASE_URL || 'https://host.docker.internal:27124',
      OBSIDIAN_VERIFY_SSL: process.env.OBSIDIAN_VERIFY_SSL || 'false',
      // Critical: bypass OneCLI proxy for loopback (see "Why this is non-obvious")
      NO_PROXY: 'host.docker.internal,127.0.0.1,localhost',
      no_proxy: 'host.docker.internal,127.0.0.1,localhost',
    },
  };
}
```

Then in the `query({ options: { ... } })` call, replace the inline `mcpServers: { nanoclaw: ... }` with `mcpServers,` and add `'mcp__obsidian__*'` to the `allowedTools` array.

We use `node <absolute-path>` instead of the `obsidian-mcp-server` bin shim so we don't depend on PATH resolution from inside the SDK's spawn.

### 2d. `.env` — store the credentials

```bash
OBSIDIAN_API_KEY=<your-api-key-from-the-plugin>
OBSIDIAN_BASE_URL=https://host.docker.internal:27124
```

Then sync to the container env file:
```bash
cp .env data/env/env
```

## Phase 3: Build and restart

```bash
./container/build.sh        # rebuild image with obsidian-mcp-server preinstalled
npm run build               # rebuild host TypeScript
launchctl kickstart -k gui/$(id -u)/com.nanoclaw   # macOS
# Linux: systemctl --user restart nanoclaw
```

If the agent has an active container, stop it so the next message starts a fresh one with the new env:
```bash
docker ps --format "{{.Names}}" | grep nanoclaw | xargs -r docker stop
```

If the agent has cached conversation state where it already concluded "vault not mounted", clear its session so it rediscovers the available tools:
```bash
sqlite3 store/messages.db "DELETE FROM sessions WHERE group_folder='<your-group-folder>'"
```

## Phase 4: Verify

Send a message in the relevant chat:

> "옵시디언에 어떤 노트가 있는지 알려줘"  /  "list the notes in my obsidian vault"

The agent should call one of the `mcp__obsidian__*` tools (e.g. `obsidian_global_search`, `obsidian_read_note`) and return real notes from your vault. If it instead asks you for a vault path, the MCP server didn't get registered — see troubleshooting below.

## Troubleshooting

### Agent says "vault is not mounted" or asks for a path

The obsidian MCP server is failing to register or returning no tools. Check, in this order:

1. **Is the MCP server even attempting to start?** Look at the active container's debug log:
   ```bash
   docker ps --format "{{.Names}}" | grep nanoclaw | head -1 | xargs docker logs 2>&1 | grep -i obsidian
   ```
   You should see `Obsidian MCP: registering server (base=...)`. If not, `OBSIDIAN_API_KEY` isn't reaching the agent-runner — re-check phase 2b/2d.

2. **Did the server crash on startup?** Check its own Winston log inside the container:
   ```bash
   docker exec <container> tail -20 /usr/local/lib/node_modules/obsidian-mcp-server/logs/error.log
   ```
   The two failure modes we've hit:
   - `EACCES` / `process.exit(1)` with no stderr → logs dir not writable. Re-check the Dockerfile chmod (phase 2a).
   - `Obsidian API Bad Request: ""` (status 400) → axios is being routed through the OneCLI proxy. Re-check that `NO_PROXY` is set in the obsidian MCP env block (phase 2c).

3. **Is Obsidian Desktop actually running on the host?** The Local REST API plugin only runs while the app is open. From the host:
   ```bash
   curl -ks -H "Authorization: Bearer $OBSIDIAN_API_KEY" https://127.0.0.1:27124/
   ```

4. **Is the agent reusing an old session that pre-dates the integration?** Stop the active container and clear the group's session row:
   ```bash
   docker ps --format "{{.Names}}" | grep nanoclaw | xargs docker stop
   sqlite3 store/messages.db "DELETE FROM sessions WHERE group_folder='<group>'"
   launchctl kickstart -k gui/$(id -u)/com.nanoclaw
   ```

### "Tools list" the agent sees doesn't include `mcp__obsidian__*`

Find the latest session jsonl and check its `addedNames` array:
```bash
LATEST=$(ls -t data/sessions/<group>/.claude/projects/-workspace-group/*.jsonl | head -1)
grep -o '"addedNames":\[[^]]*\]' "$LATEST" | head -1
```
If `mcp__obsidian__*` tools aren't there, the SDK launched obsidian-mcp-server but it returned no tools — meaning the server crashed during `initialize` (almost always one of the two issues in the "non-obvious" section above).

## Removal

To roll back this skill:
1. Remove the `obsidian-mcp-server` install line and the `mkdir/chmod` line from `container/Dockerfile`
2. Remove the `readEnvFile(['OBSIDIAN_*'])` block from `src/container-runner.ts`
3. Remove the obsidian entry and the `mcp__obsidian__*` allowedTools entry from `container/agent-runner/src/index.ts`
4. Remove the `OBSIDIAN_*` lines from `.env` and re-sync `data/env/env`
5. Rebuild image, host TS, and restart the service
