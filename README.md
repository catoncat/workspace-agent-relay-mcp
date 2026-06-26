# workspace-agent-relay-mcp

Local relay MCP and dashboard for ChatGPT Workspace Agent trigger runs.

The Workspace Agent trigger API accepts asynchronous work but does not currently provide a response retrieval API. This project gives the agent a narrow local MCP callback surface so it can write progress, questions, and final Markdown results back to your machine.

## Security model

- The Workspace Agent access token stays local.
- MCP write callbacks require a per-run `callback_token`.
- The MCP tools do not expose shell, arbitrary file reads, or arbitrary file writes.
- The first version is a communication bridge, not a local-ops server.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`, then run:

```bash
workspace-agent-relay-mcp
```

Local dashboard:

```text
http://127.0.0.1:8799/
```

MCP endpoint:

```text
http://127.0.0.1:8799/mcp
```
