# Workspace Agent Relay MCP Design

Date: 2026-06-26

## Goal

Build a local-first relay for ChatGPT Workspace Agents so a local operator can trigger an agent, continue a stable `conversation_key`, and receive the agent's progress, questions, and final Markdown result back on the local machine.

The relay exists because the Workspace Agent trigger API is currently an asynchronous enqueue endpoint. It can accept work, but it does not provide a public run ID or a response retrieval API. The relay provides an explicit side channel: the agent calls a local MCP tool such as `record_result`, and the local service stores the reply.

## Non-Goals

- Do not expose arbitrary shell execution.
- Do not expose unrestricted filesystem read/write.
- Do not replace ChatGPT conversation history or Workspace Agent memory.
- Do not create GitHub issues, edit repositories, or call third-party systems in the first version.
- Do not depend on scraping ChatGPT conversation pages.

## Reference Project

Use `../notion-local-ops-mcp` (the sibling repo) as an implementation reference for:

- FastMCP server structure.
- Streamable HTTP transport at `/mcp`.
- Legacy SSE compatibility fallback.
- Bearer and OAuth compatibility for ChatGPT web developer mode.
- Cloudflared tunnel scripts.
- macOS launchd support.
- MCP debug logging.
- Local end-to-end MCP tests with `mcp.client.streamable_http`.

Do not copy its broad local-ops tool surface. That project intentionally grants filesystem, shell, git, patch, and delegated coding power. This relay should be much narrower.

## Product Shape

The first usable version has two local surfaces:

1. A local web app for the human operator.
2. A local MCP server exposed to the Workspace Agent through the already-working MCP/tunnel setup.

The web app lets the user:

- Register one or more Workspace Agent trigger endpoints.
- Store the Workspace Agent access token locally.
- Create or select a logical conversation.
- Send a task to the agent.
- See the `request_id`, API status, `x-request-id`, and `conversation_url`.
- Watch progress events and user questions.
- Read the final Markdown result recorded through MCP.
- Continue the same `conversation_key` with a follow-up.

The MCP server lets the agent:

- Record progress.
- Record a final result.
- Ask the user a question.
- Read bounded recent context for the same conversation.

## Security Model

### Local Secrets

The Workspace Agent access token must never be sent to the browser client. It lives in a local `.env` file or local state file readable only by the current OS user.

The MCP bearer or OAuth login token must also be local-only and excluded from git.

### Per-Run Callback Token

Each trigger run gets:

- `request_id`: stable local run identifier.
- `callback_token`: random one-time token.
- `conversation_key`: stable conversation identifier.
- `idempotency_key`: normally equal to `request_id`.

The local backend injects `request_id`, `conversation_key`, and `callback_token` into the trigger input. Every write MCP tool must require the same `request_id` and `callback_token`.

The relay accepts a write only when:

- The `request_id` exists.
- The run is still open for callbacks.
- The `callback_token` matches.
- The target `conversation_key` matches the stored run.

This prevents a different ChatGPT conversation, stale prompt, or accidental tool call from writing into the wrong run.

### Tool Boundary

Initial MCP tools are communication-only. They do not read local code, run commands, or write arbitrary files.

Allowed write tools:

- `record_progress`
- `record_result`
- `ask_user`

Allowed read tools:

- `get_run_context`
- `server_info`

Future repo-reading tools must be separate, opt-in, and directory allowlisted.

## Data Model

Use SQLite under `STATE_DIR`, defaulting to `~/.workspace-agent-relay-mcp/relay.sqlite`.

### agents

- `id`
- `name`
- `trigger_url`
- `trigger_id`
- `token_ref`
- `created_at`
- `updated_at`

`token_ref` points to local secret storage. MVP can keep tokens in `.env` by agent name; a later version can use an owner-only JSON secret file.

### conversations

- `id`
- `agent_id`
- `name`
- `conversation_key`
- `created_at`
- `updated_at`
- `archived_at`

### runs

- `id`
- `request_id`
- `agent_id`
- `conversation_id`
- `conversation_key`
- `callback_token_hash`
- `idempotency_key`
- `input_markdown`
- `trigger_status`
- `trigger_http_status`
- `trigger_x_request_id`
- `conversation_url`
- `status`
- `created_at`
- `updated_at`
- `completed_at`

`status` values:

- `draft`
- `sent`
- `accepted`
- `waiting`
- `needs_user`
- `done`
- `blocked`
- `failed`

### events

- `id`
- `run_id`
- `request_id`
- `event_type`
- `title`
- `markdown`
- `payload_json`
- `created_at`

`event_type` values:

- `trigger_sent`
- `trigger_accepted`
- `trigger_failed`
- `progress`
- `question`
- `result`
- `system`

### artifacts

- `id`
- `run_id`
- `name`
- `mime_type`
- `content`
- `metadata_json`
- `created_at`

The MVP stores text artifacts only.

## MCP Tools

### `server_info`

Returns app metadata, transport, state dir, auth mode, tool names, and version.

### `record_progress`

Arguments:

```json
{
  "request_id": "run_...",
  "callback_token": "secret per-run value",
  "conversation_key": "research:catoncat-sherlog",
  "message": "Short progress update",
  "title": "optional title",
  "payload": {}
}
```

Behavior:

- Validate callback.
- Append a `progress` event.
- Move run status to `waiting` unless it is already terminal.
- Return `{ "success": true, "event_id": ... }`.

### `record_result`

Arguments:

```json
{
  "request_id": "run_...",
  "callback_token": "secret per-run value",
  "conversation_key": "research:catoncat-sherlog",
  "status": "done",
  "title": "Sherlog roadmap issues",
  "markdown": "Full final response",
  "artifacts": [
    {
      "name": "roadmap.md",
      "mime_type": "text/markdown",
      "content": "# Roadmap"
    }
  ]
}
```

Behavior:

- Validate callback.
- Append a `result` event.
- Store artifacts.
- Set run status to `done`, `blocked`, or `failed`.
- Set `completed_at`.
- Return `{ "success": true, "run_status": ... }`.

### `ask_user`

Arguments:

```json
{
  "request_id": "run_...",
  "callback_token": "secret per-run value",
  "conversation_key": "research:catoncat-sherlog",
  "question": "Which repo should I inspect?",
  "choices": ["A", "B"],
  "context": "Why the question matters"
}
```

Behavior:

- Validate callback.
- Append a `question` event.
- Set run status to `needs_user`.
- Return a local question identifier.

The human answer is not returned through the same MCP call. The web app sends a follow-up trigger using the same `conversation_key`, referencing the question and parent `request_id`.

### `get_run_context`

Arguments:

```json
{
  "conversation_key": "research:catoncat-sherlog",
  "limit": 5
}
```

Behavior:

- Return recent run summaries, questions, and final result titles for the conversation.
- Cap output by count and byte size.
- Do not return callback tokens.
- Do not return Workspace Agent access tokens.

This helps the Workspace Agent orient itself if its ChatGPT conversation state is incomplete.

## Trigger Input Contract

Every API trigger created by the relay includes a structured header:

```text
request_id: <request_id>
conversation_key: <conversation_key>
callback_token: <callback_token>
relay_mcp: workspace-agent-relay-mcp

Completion contract:
Before you finish, call workspace-agent-relay-mcp.record_result with the exact request_id, conversation_key, callback_token, status, title, and full Markdown result.
Use record_progress for meaningful progress updates.
Use ask_user if you are blocked on a user decision.
Do not only answer in the ChatGPT conversation.
```

Then the user's task follows.

## HTTP Backend

The web app backend owns:

- Agent configuration.
- Token lookup.
- Request ID generation.
- Callback token generation and hashing.
- Trigger API call.
- Run/event persistence.
- Local HTTP API for the frontend.

Initial endpoints:

- `GET /api/agents`
- `POST /api/agents`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/:id/runs`
- `POST /api/conversations/:id/runs`
- `GET /api/runs/:id`
- `POST /api/runs/:id/follow-up`

The backend can use Server-Sent Events or polling for UI updates. MVP can poll every 2 seconds.

## Frontend

Build a utilitarian local dashboard, not a landing page.

Layout:

- Left column: agents and conversations.
- Main column: run timeline and final result.
- Bottom composer: task input, send button, follow-up mode.
- Right details panel: request metadata, conversation URL, status, copy buttons.

States:

- No agent configured.
- No conversation selected.
- Draft input.
- Trigger pending.
- Accepted and waiting.
- Needs user input.
- Done/blocked/failed.

The UI should make `conversation_key` visible and editable because it is the durable thread identity.

## Implementation Stack

Use Python 3.11+ and FastMCP to stay close to `notion-local-ops-mcp`.

Recommended server package:

- `fastmcp>=3.2.4,<4`
- `uvicorn>=0.30.0`
- standard-library `sqlite3`

Recommended frontend:

- Vite + React + TypeScript
- local backend serves static frontend in production
- development can run frontend and backend separately

If speed matters, the first working version may serve a minimal static HTML/JS page from the Python backend. The React UI can be added after the MCP callback loop is proven.

## Project Layout

```text
workspace-agent-relay-mcp/
  pyproject.toml
  README.md
  .env.example
  src/workspace_agent_relay_mcp/
    __init__.py
    config.py
    db.py
    relay.py
    server.py
    http_compat.py
    oauth.py
    trigger.py
    web.py
  web/
    package.json
    src/
  scripts/
    dev-tunnel.sh
    install-launchd.sh
    launchd-status.sh
  tests/
    test_relay_store.py
    test_mcp_callbacks.py
    test_trigger_payload.py
    test_server_transport.py
  docs/
    superpowers/specs/
```

`http_compat.py` and `oauth.py` can initially be adapted from `notion-local-ops-mcp` with names, descriptions, scopes, and environment variables changed.

## Environment Variables

Use a distinct prefix:

- `WORKSPACE_AGENT_RELAY_HOST`
- `WORKSPACE_AGENT_RELAY_PORT`
- `WORKSPACE_AGENT_RELAY_STATE_DIR`
- `WORKSPACE_AGENT_RELAY_AUTH_TOKEN`
- `WORKSPACE_AGENT_RELAY_AUTH_MODE`
- `WORKSPACE_AGENT_RELAY_PUBLIC_BASE_URL`
- `WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN`
- `WORKSPACE_AGENT_RELAY_OAUTH_SCOPES`
- `WORKSPACE_AGENT_RELAY_OAUTH_TOKEN_TTL_SECONDS`
- `WORKSPACE_AGENT_RELAY_DEBUG_MCP_LOGGING`
- `WORKSPACE_AGENT_RELAY_AGENT_TOKEN`
- `WORKSPACE_AGENT_RELAY_TRIGGER_URL`

MVP can support a single default agent via env vars, then later add persistent multi-agent config.

## Verification Plan

### Unit Tests

- Callback validation rejects missing or wrong tokens.
- `record_progress` creates a progress event.
- `record_result` closes a run and stores Markdown.
- `ask_user` moves a run to `needs_user`.
- `get_run_context` redacts callback tokens and secrets.
- Trigger payload includes completion contract.

### MCP Integration Tests

Start the server on a random local port and call tools through `mcp.client.streamable_http`.

Tests:

- Initialize and list tools.
- Call `record_result` for a valid run.
- Reject `record_result` for wrong callback token.
- Call `get_run_context` after a completed run.

### Manual Smoke Test

1. Start local relay MCP and tunnel.
2. Connect it to ChatGPT or the Workspace Agent environment.
3. Create a run through the local web app.
4. Trigger the Workspace Agent.
5. Confirm the agent calls `record_result`.
6. Confirm the local web app shows the full Markdown result.

## Risks

- The Workspace Agent may ignore the callback instruction. Mitigation: make the completion contract explicit in every trigger input and in the Workspace Agent's saved instructions.
- ChatGPT tool names may be ambiguous if multiple MCPs are enabled. Mitigation: use a distinctive server name and explicit prompt wording.
- MCP tunnel or OAuth setup may drift. Mitigation: reuse the tested compatibility and launchd patterns from `notion-local-ops-mcp`.
- Long final Markdown may exceed tool argument limits. Mitigation: store artifacts separately and support chunked `append_result_chunk` later if needed.
- A leaked callback token could allow writing to one open run. Mitigation: high-entropy token, per-run scope, token hash at rest, short callback expiry, no secrets in read tools.

## Later Enhancements

- Chunked result upload for very long artifacts.
- Browser notification when a run asks a user question.
- Destination adapters for GitHub issues, Google Sheets, Slack, or Notion.
- Allowlisted project context tools.
- Search over local run history.
- Multiple Workspace Agents with per-agent prompt templates.
- Automatic retry with idempotency keys.
- Secure MCP Tunnel support if available in the user's environment.

## Acceptance Criteria For MVP

- A user can configure one Workspace Agent trigger URL and access token locally.
- A user can create a conversation with a stable `conversation_key`.
- A user can send a task and receive a successful `202 Accepted` trigger result.
- The generated trigger input includes `request_id`, `conversation_key`, `callback_token`, and the completion contract.
- The MCP server exposes `record_progress`, `record_result`, `ask_user`, `get_run_context`, and `server_info`.
- A valid `record_result` call stores the full final Markdown locally and marks the run complete.
- An invalid callback token is rejected.
- The local web page displays runs, progress, questions, final result Markdown, and `conversation_url`.
- Tests cover store behavior, callback validation, MCP tool calls, and trigger payload construction.
