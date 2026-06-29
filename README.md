# workspace-agent-relay-mcp

Local relay + dashboard for ChatGPT **Workspace Agents**: the agent reports plan, progress, tool calls, and results back to your machine in real time.

<img width="1461" height="1057" alt="image" src="https://github.com/user-attachments/assets/2113f985-801f-4a79-a75c-6650f0563940" />


<img width="1461" height="1057" alt="image" src="https://github.com/user-attachments/assets/82f6a6b3-6e75-4747-b6e1-5c526ddaaf12" />

<img width="1256" height="2760" alt="image" src="https://github.com/user-attachments/assets/d10ff072-639b-4b02-8302-d401127ce800" />

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
- **Dashboard IA** — conversations are organized by Workspace (`working_directory`) or the built-in `无目录` space. Workspace Agent entries are execution backends selected in Settings, not the primary sidebar object.

The active code path is intentionally relay-only: MCP callback events plus local tool traces. Older cloud-side readback experiments have been removed from the working tree; use Git history if you need to study them.

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

### 1. Register an execution backend in the relay dashboard

**Settings → Add backend** (or use `.env` for a single default backend):

| Field | Where to get it |
| --- | --- |
| Name | Your label (e.g. Work, Personal) |
| Trigger URL | ChatGPT → Workspace Agent → `https://api.chatgpt.com/v1/workspace_agents/agtch_…/trigger` |
| Access token | Same settings page (`at-…`) — stored on the relay, never shown again in the browser |

For multiple ChatGPT accounts, add one backend row per account. Pick the **Current backend** in Settings; new threads use that backend automatically.

### 2. Configure workspaces

Use the sidebar workspace selector or **Settings → Workspaces**:

- `无目录` is built in and sends no cwd.
- A workspace has a name and an absolute `working_directory`.
- New threads inherit the current workspace.
- Every run stores a `working_directory` snapshot and injects it into the Workspace Agent trigger, so later workspace path edits do not rewrite old runs.

### 3. Connect MCP: relay (required)

In the Workspace Agent → **MCP connectors**:

| Field | Value |
| --- | --- |
| URL | `http://127.0.0.1:8799/mcp` (or your tunnel `/mcp`) |
| Auth | Bearer = `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` |

Confirm tools: `record_plan`, `record_progress`, `record_result`, `ask_user`, `get_run_context`, `server_info`.

### 4. Connect MCP: local ops (recommended)

Add [notion-local-ops-mcp](https://github.com/catoncat/notion-local-ops-mcp) as a second connector so **Tool calls** stream in the dashboard. See its README for URL/auth.

### 5. Paste Agent Instructions (easy to miss)

Open **[`docs/agent-instructions.md`](docs/agent-instructions.md)**:

1. Replace placeholders `<YOUR_RELAY_MCP>` and `<YOUR_LOCAL_OPS_MCP>` with your connector names (defaults: `workspace-agent-relay-mcp` and `notion-local-ops-mcp`).
2. Copy the fenced **指令正文** block.
3. ChatGPT → edit Workspace Agent → **Instructions** → paste (append or replace any old relay section).

Expected workflow:

```
record_plan  →  bind_relay_run  →  batch record_progress  →  record_result
```

Without this paste, the agent may work only inside ChatGPT and the operator sees nothing on the relay.

### 6. Smoke test

Select a workspace, then send a short task from the dashboard (e.g. inspect the current directory or create/read a file under `/tmp`). You should see plan → tool traces (if local-ops connected) → result, and the trigger should include `working_directory` for non-`无目录` workspaces.

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
2. Agent calls `bind_relay_run` on **notion-local-ops-mcp** with `request_id` (+ `conversation_key`) from the trigger (no `relay_url` needed when configured locally).
3. Traced tools POST to `/internal/tool-trace` on this relay (shared bearer) → dashboard.

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
- `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` — dashboard + `/mcp` bearer, and the shared bearer for `/internal/tool-trace` (the notion-local-ops bridge). When unset, `/internal/tool-trace` is disabled.
- Workspace Agent access tokens — stored in relay DB or `.env`; rotate if leaked.
- MCP tool writes route by `request_id` + `conversation_key` and are rejected once a run is terminal (`done`/`blocked`/`failed`/`superseded`).
- Dashboard sends default to queue/new request: Enter creates a fresh `request_id` and does not close the current active run. Explicit steer/guidance reuses the selected active run's `request_id`.
- Workspace paths are plain absolute local paths. They are copied into each run as `working_directory_snapshot`; old runs are not rewritten when a workspace is edited or deleted.

## Status

Local-first prototype for learning the Workspace Agent callback gap — not a product.
