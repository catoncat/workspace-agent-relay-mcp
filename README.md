# workspace-agent-relay-mcp

Local relay MCP and dashboard for ChatGPT Workspace Agent trigger runs.

The Workspace Agent trigger API accepts asynchronous work but does not currently provide a response retrieval API. This project gives the agent a narrow local MCP callback surface so it can write progress, questions, and final Markdown results back to your machine.

## What It Exposes

MCP tools:

- `record_progress`
- `record_result`
- `ask_user`
- `get_run_context`
- `server_info`

It intentionally does not expose shell, arbitrary file reads, git, or arbitrary file writes.

## Trigger Semantics

Workspace Agent continuation is controlled by the trigger request body `conversation_key`.

- `conversation_key` is the stable continuation key for a business object or thread.
- `request_id` is a per-run trace key included in the input and callback payloads.
- `idempotency_key` is a per-trigger-event retry key. New logical messages should use a new key.
- `conversation_url` is saved as observational metadata for humans. It is not the continuation key.

The dashboard shows both the current continuation key and the most recent conversation URL so operators do not accidentally start a new conversation by reusing the wrong identifier.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`:

```bash
WORKSPACE_AGENT_RELAY_AUTH_TOKEN=local-mcp-token
WORKSPACE_AGENT_RELAY_TRIGGER_URL=https://api.chatgpt.com/v1/workspace_agents/agtch_your_id/trigger
WORKSPACE_AGENT_RELAY_AGENT_TOKEN=your-workspace-agent-access-token
```

Run locally:

```bash
workspace-agent-relay-mcp
```

Dashboard:

```text
http://127.0.0.1:8799/
```

MCP endpoint:

```text
http://127.0.0.1:8799/mcp
```

Run with a tunnel:

```bash
./scripts/dev-tunnel.sh
```

## Workspace Agent Instruction

Add an instruction like this to the Workspace Agent:

```text
When a trigger input includes request_id, conversation_key, and callback_token, use the workspace-agent-relay-mcp tools.

Before you finish, call record_result with:
- exact request_id
- exact conversation_key
- exact callback_token
- status
- title
- full Markdown result

Use record_progress for meaningful progress.
Use ask_user when blocked on a user decision.
Do not only answer in the ChatGPT conversation.
```

## Smoke Test

1. Start the relay.
2. Connect the MCP endpoint to ChatGPT or the Workspace Agent runtime.
3. Open the dashboard.
4. Create or load the default agent.
5. Send a short task.
6. Confirm the dashboard shows `accepted`.
7. Confirm the agent calls `record_result`.
8. Confirm final Markdown appears in the dashboard.

## Security Notes

- Keep `.env` out of git.
- Rotate any Workspace Agent access token pasted into chat or logs.
- Use a high-entropy `WORKSPACE_AGENT_RELAY_AUTH_TOKEN`.
- The callback token is per-run and is stored only as a hash.
- Debug MCP logging redacts common token, secret, authorization, and key fields before writing summaries.
