# workspace-agent-relay-mcp

Local relay + dashboard for ChatGPT **Workspace Agents**: the agent reports plan, progress, tool calls, and results back to your machine in real time.

![Relay dashboard mirroring a ChatGPT Workspace Agent run](https://github.com/user-attachments/assets/cea599fe-9c2f-499e-86d5-c43ea170cc7d)

> **Why:** the Workspace Agent trigger API is fire-and-forget (`202` with no body). This relay gives the agent an MCP callback channel and you a live dashboard.

## Architecture

```
you (browser)     your machine                         ChatGPT
┌──────────┐    ┌─────────────────────────┐        ┌─────────────────┐
│ dashboard│◀── │ workspace-agent-relay-mcp│ ◀─MCP── │ Workspace Agent │
│  :8799   │    │  (this repo)            │        └─────────────────┘
└──────────┘    └───────────┬─────────────┘
                            │ tool-trace POST
                            ▲
                   ┌────────┴────────────┐
                   │ notion-local-ops-mcp │  optional: files / shell / git
                   └─────────────────────┘
```

- **This repo** — reporting MCP (`record_plan`, `record_progress`, `record_result`, …) + dashboard + SSE.
- **[notion-local-ops-mcp](https://github.com/catoncat/notion-local-ops-mcp)** (optional) — execution tools; `bind_relay_run` mirrors tool calls here.

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set WORKSPACE_AGENT_RELAY_AUTH_TOKEN at minimum
workspace-agent-relay-mcp
```

Open `http://127.0.0.1:8799/`, enter the relay **access password** (`WORKSPACE_AGENT_RELAY_AUTH_TOKEN`).

Tunnel (optional): `./scripts/dev-tunnel.sh`

## Local development (recommended)

For day-to-day UI work you do **not** need `pnpm run build`. The Python server serves a static `frontend/dist` bundle on `:8799` — that path is production-like and requires a rebuild after every change.

Instead, run the backend and the Vite dev server separately:

```bash
# Terminal 1 — API + MCP + SSE (launchd/dev-tunnel is fine too)
.venv/bin/python -m workspace_agent_relay_mcp.server

# Terminal 2 — dashboard with HMR
./scripts/dev-dashboard.sh
```

Open **`http://127.0.0.1:5173`** for the dashboard. ChatGPT MCP stays on **`http://127.0.0.1:8799/mcp`** (or your tunnel URL).

`dev-dashboard.sh` checks that the relay is healthy, then starts Vite. It reads `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` from the repo `.env` and seeds the browser token automatically — no need to paste it again on `:5173`.

| URL | Purpose |
| --- | --- |
| `http://127.0.0.1:5173` | Dashboard while editing frontend (HMR) |
| `http://127.0.0.1:8799` | API, MCP, SSE; static dashboard if `frontend/dist` exists |
| tunnel `/mcp` | ChatGPT Workspace Agent connector |

Run `cd frontend && pnpm run build` only before CI or when you want the single-port `:8799` dashboard without Vite.

## ChatGPT Workspace Agent setup (required)

Without these four steps the dashboard stays empty.

### 1. Register the agent in the relay dashboard

**Settings → Add agent** (or use `.env` for a single default agent):

| Field | Where to get it |
| --- | --- |
| Name | Your label (e.g. Work, Personal) |
| Trigger URL | ChatGPT → Workspace Agent → `https://api.chatgpt.com/v1/workspace_agents/agtch_…/trigger` |
| Access token | Same settings page (`at-…`) — stored on the relay, never shown again in the browser |

For multiple ChatGPT accounts, add one agent row per account. Pick the agent when creating a thread in the sidebar.

### 2. Connect MCP: relay (required)

In the Workspace Agent → **MCP connectors**:

| Field | Value |
| --- | --- |
| URL | `http://127.0.0.1:8799/mcp` (or your tunnel `/mcp`) |
| Auth | Bearer = `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` |

Confirm tools: `record_plan`, `record_progress`, `record_result`, `ask_user`, `get_run_context`, `server_info`.

### 3. Connect MCP: local ops (recommended)

Add [notion-local-ops-mcp](https://github.com/catoncat/notion-local-ops-mcp) as a second connector so **Tool calls** stream in the dashboard. See its README for URL/auth.

### 4. Paste Agent Instructions (easy to miss)

Open **[`docs/agent-instructions.md`](docs/agent-instructions.md)**:

1. Replace placeholders `<YOUR_RELAY_MCP>` and `<YOUR_LOCAL_OPS_MCP>` with your connector names (defaults: `workspace-agent-relay-mcp` and `notion-local-ops-mcp`).
2. Copy the fenced **指令正文** block.
3. ChatGPT → edit Workspace Agent → **Instructions** → paste (append or replace any old relay section).

Expected workflow:

```
record_plan  →  bind_relay_run  →  batch record_progress  →  record_result
```

Without this paste, the agent may work only inside ChatGPT and the operator sees nothing on the relay.

### 5. Smoke test

Send a short task from the dashboard (e.g. create and read a file under `/tmp`). You should see plan → tool traces (if local-ops connected) → result.

## MCP tools (relay)

| Tool | Purpose |
| --- | --- |
| `record_plan` | Step plan at turn start (stable step ids) |
| `record_progress` | Batched step updates + optional note |
| `record_result` | Final Markdown + status (`done` / `failed` / `blocked`) |
| `ask_user` | Pause for a human decision |
| `get_run_context` | Recover run summary if context drifts |

## Dashboard

Per run: your message → plan checklist → tool traces (from local-ops) → progress notes → `ask_user` (if any) → final result. Updates via SSE (no refresh).

## Pairing with notion-local-ops-mcp

1. Agent calls `record_plan` on **this relay**.
2. Agent calls `bind_relay_run` on **notion-local-ops-mcp** with `request_id` + `callback_token` from the trigger (no `relay_url` needed when configured locally).
3. Traced tools POST to `/internal/tool-trace` on this relay → dashboard.

Details: [notion-local-ops-mcp → Relay Bridge](https://github.com/catoncat/notion-local-ops-mcp#relay-bridge-mirror-tool-calls-to-a-dashboard).

## Project layout

```
src/workspace_agent_relay_mcp/   server, MCP tools, API, SQLite store, trigger client
frontend/                        React dashboard
docs/agent-instructions.md       paste block for ChatGPT Instructions
scripts/dev-tunnel.sh            cloudflared supervisor
scripts/dev-dashboard.sh         Vite HMR dashboard (proxies /api → relay)
tests/
```

## Security

- Never commit `.env`, tunnels, or `*.sqlite*`.
- `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` — dashboard + `/mcp` bearer.
- Workspace Agent access tokens — stored in relay DB or `.env`; rotate if leaked.
- Per-run `callback_token` stored hashed only; redacted in API/logs.

## Status

Local-first prototype for learning the Workspace Agent callback gap — not a product.
