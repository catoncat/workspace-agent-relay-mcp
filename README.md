# workspace-agent-relay-mcp

A local relay + dashboard that lets a ChatGPT **Workspace Agent** report its plan, progress, tool calls, questions, and final result back to your machine — in real time, while it works.

> Why this exists: the Workspace Agent **trigger API** is fire-and-forget. You POST a task and get a `202 Accepted` with no body and no way to retrieve the agent's answer. So an agent running in ChatGPT has no built-in channel to show you what it's doing or hand you a result. This relay gives it that channel: a tiny MCP server the agent calls back into, plus a live dashboard you watch.

## How it fits together

Three pieces, two of them on your machine:

```
   you (browser)            your machine                       ChatGPT cloud
   ┌────────────┐    ┌──────────────────────────┐         ┌──────────────────┐
   │ dashboard  │◀── │  workspace-agent-relay    │ ◀──MCP─ │  Workspace Agent │
   │ :8799      │    │  (MCP + web + SSE)        │  calls  │  (triggered runs)│
   └────────────┘    └─────────────┬────────────┘         └──────────────────┘
                                   │ HTTP /internal/tool-trace
                                   ▲
                                   │  fire-and-forget trace per tool call
                          ┌────────┴─────────────┐
                          │ notion-local-ops-mcp │  ← the agent's "hands"
                          │ (file/git/shell tools)│     (separate repo, optional)
                          └──────────────────────┘
```

- **workspace-agent-relay-mcp** (this repo): the MCP server the agent writes into, the dashboard you read from, and the SSE bus that pushes updates live.
- **notion-local-ops-mcp** (separate repo, optional): the agent's *working* tools — files, git, shell. When paired with this relay, every tool call the agent makes there is auto-mirrored here as a trace, so you watch it work without the agent manually reporting anything.
- **ChatGPT Workspace Agent**: the cloud brain. Triggered by this relay, calls back into both MCPs.

## What the agent sees (MCP tools)

Six tools, all narrow on purpose — no shell, no arbitrary file access, no secrets:

| Tool | When the agent calls it |
| --- | --- |
| `record_plan` | At the start of a run, with its step plan (stable ids + titles). |
| `record_progress` | After a few steps, batch-updating step statuses + an optional one-line note. |
| `record_result` | Once at the end, with `status` (done/blocked/failed), title, and full Markdown. |
| `ask_user` | Only when genuinely blocked on a human decision. |
| `get_run_context` | To recover the current run's summary if it loses context. |
| `server_info` | Introspection — relay URL, auth mode, registered tools. |

## What you see (dashboard)

Open `http://127.0.0.1:8799/` in a browser. For each run, in reading order:

1. **Your message** (what you sent the agent).
2. **Plan checklist** — the steps the agent committed to, with live `in_progress / done / skipped` states.
3. **Tool calls** — a collapsible list of tool-call traces auto-mirrored from the agent's working MCP (apply_patch, git_commit, run_command, …), each with args, result summary, and duration. Failed calls are flagged red.
4. **Notes** — the agent's own one-line progress narrations (only when it has something worth saying).
5. **Question** — if the agent asked you something via `ask_user`.
6. **Result** — the final Markdown deliverable.

Everything streams in over SSE while the agent works — you don't refresh.

## Quick start

### 1. Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### 2. Configure `.env`

```bash
# Protects /api/* and /mcp. Generate with: openssl rand -hex 32
WORKSPACE_AGENT_RELAY_AUTH_TOKEN=replace-me

# From your ChatGPT Workspace Agent settings:
WORKSPACE_AGENT_RELAY_TRIGGER_URL=https://api.chatgpt.com/v1/workspace_agents/agtch_your_id/trigger
WORKSPACE_AGENT_RELAY_AGENT_TOKEN=your-workspace-agent-access-token
```

Two tokens, two jobs:

| Variable | Protects | Lives in |
| --- | --- | --- |
| `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` | `/api/*` and `/mcp` | `.env` **and** the dashboard "Relay API Token" field |
| `WORKSPACE_AGENT_RELAY_AGENT_TOKEN` | Outbound trigger calls to ChatGPT | `.env` only — never the browser |

### 3. Run

```bash
workspace-agent-relay-mcp        # serves MCP + dashboard on 127.0.0.1:8799
```

Or behind a tunnel:

```bash
./scripts/dev-tunnel.sh          # uses cloudflared if cloudflared.local.yml exists, else a quick tunnel
```

### 4. Wire it into ChatGPT

- Add the MCP endpoint (`http://127.0.0.1:8799/mcp` locally, or your tunnel URL) to your Workspace Agent's MCP connectors.
- Paste the relay collaboration instruction from [`docs/agent-instructions.md`](docs/agent-instructions.md) into the Agent's **Instructions** field. That tells the agent to `record_plan` → `bind_relay_run` → batch `record_progress` → `record_result`.

### 5. Smoke test

1. Start the relay, open the dashboard, paste the auth token.
2. Send a short task from the dashboard.
3. Watch the plan checklist appear, tool traces stream in, then the final result.

## Tool-call mirroring (pairing with notion-local-ops-mcp)

This is the part that makes the dashboard feel *live* instead of a silence-then-bang.

1. The agent calls `record_plan` on this relay (its plan shows up).
2. The agent calls `bind_relay_run` on **notion-local-ops-mcp**, passing the `request_id` + `callback_token` from the trigger. It does **not** pass a relay URL — that's already configured locally (`NOTION_LOCAL_OPS_RELAY_URL`, default `http://127.0.0.1:8799`).
3. From then on, every tool the agent runs on notion-local-ops fires a fire-and-forget `POST /internal/tool-trace` to this relay.
4. This relay stores each trace as a progress event and pushes it over SSE to the dashboard.

The internal endpoint authenticates with the per-run `callback_token` in the body (not the dashboard bearer), and a closed/terminal run rejects traces with `409`. The relay being unreachable never blocks the agent's tool execution — traces are best-effort.

## Project layout

```
src/workspace_agent_relay_mcp/
  server.py        # FastMCP server + the six agent-facing tools + global instructions
  app.py           # Starlette app: routes, middleware, SSE event bus
  api/routes/      # /api/agents, /api/conversations, /api/runs (SSE), /internal/tool-trace
  store/relay_store.py   # SQLite layer: runs, events, plans, artifacts, redaction
  trigger.py       # Builds the input_text sent to the ChatGPT trigger API
  config.py        # Env-driven config
  oauth.py         # Optional OAuth mode for ChatGPT web developer mode
frontend/          # React + Vite dashboard (TypeScript, TanStack Query, SSE)
scripts/dev-tunnel.sh   # supervisor + cloudflared rolling-reload launcher
docs/              # design specs + agent instructions
tests/             # pytest suite
```

## Trigger semantics (the short version)

- `conversation_key` — the stable continuation key for a thread. Reuse it to keep one conversation.
- `request_id` — per-run trace key, echoed in every callback.
- `idempotency_key` — per-message retry key. New logical message → new key.
- `conversation_url` — saved as human-readable metadata only; not the continuation key.

The dashboard shows both the current `conversation_key` and the latest `conversation_url` so you don't accidentally fork a thread by reusing the wrong one.

## Security notes

- `.env`, `cloudflared.local.yml`, and `*.sqlite*` are git-ignored — keep them out of commits.
- The per-run `callback_token` is stored only as a hash; it's redacted from logs and API responses.
- Use a high-entropy `WORKSPACE_AGENT_RELAY_AUTH_TOKEN`.
- Rotate any Workspace Agent access token that ever leaks into chat or logs.
- Debug MCP logging redacts common token/secret/authorization/key fields before writing summaries.

## Status

Early, single-user, local-first. Not a product. Built to learn and prototype the Workspace Agent callback gap.
