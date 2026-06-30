# Local Agent Shell Protocol

Date: 2026-06-30

## Problem

The relay is becoming a local Codex-style shell for ChatGPT Workspace Agents. The missing pieces are not more behavioral instructions; they are explicit local entities and tools:

- user-selected local files (`@file`)
- local relay conversations as addressable context
- local skills metadata available at conversation start
- a compact trigger protocol that carries those entities without dumping contents

Non-goal: implement imagined context objects such as `@folder`, `@diff`, terminal/session selections, image return channels, memory flows, or native remote agent-to-agent `@`.

## Principle

如无必要，不增实体。

An entity is justified only when it gives the remote Workspace Agent a stable local reference it cannot otherwise recover. The relay should provide clear references and tools; it should not over-prescribe how the agent reasons.

## Trigger protocol shape

Every trigger input remains plain text because the Workspace Agent trigger API accepts text. The relay renders a stable, parseable text envelope:

```text
request_id: relay_...
conversation_key: ...
relay_mcp: workspace-agent-relay-mcp
protocol: local-agent-shell/v1
turn_mode: initial|continuation|steer|answer
working_directory: /absolute/path  # optional

Local context:
selected_files:
  - path: /absolute/path/src/foo.py
    workspace_relative_path: src/foo.py
    content: not_included
    reason: user_selected
available_skills:
  - name: diagnose
    description: Disciplined diagnosis loop...
    path: /Users/envvar/.agents/skills/diagnose/SKILL.md
    scope: global
related_local_conversations:
  - conversation_key: workspace:topic
    title: Previous thread
    read_tool: workspace-agent-relay-mcp.read_local_conversation
```

Rules:

1. `selected_files` are per trigger and may appear on initial, continuation, steer, or answer triggers.
2. `selected_files` contain references only. The relay does not include file contents by default.
3. `available_skills` is rendered only for the first queued/new run of a local conversation.
4. Continuation/steer/answer triggers do not repeat the full skills prelude.
5. `related_local_conversations` are references to relay-stored conversations. Conversation content is fetched through MCP tools, not embedded unbounded in every trigger.
6. If a section has no entities, omit the section.

The existing relay workflow remains:

- initial new conversation: `update_conversation_title` once, then `record_plan`
- every turn: `record_plan` -> attempt `bind_relay_run` -> `record_progress` -> `ask_user` or `record_result`
- steer/answer reuse the same `request_id`
- plan changes use `record_plan` / `step_updates`, not `record_result`
- `record_result` is the final answer channel

## `@file` entity

### UI behavior

The composer supports `@` for local file selection.

MVP behavior:

- opens a workspace-scoped file browser
- allows navigating directories and selecting files
- inserts visible file chips or stable textual references
- sends structured `selected_files` with the message
- does not add unsupported context types

### Backend validation

Selected files are accepted as structured local context:

```json
{
  "input_markdown": "Please inspect this",
  "local_context": {
    "selected_files": [
      {
        "path": "/absolute/workspace/src/foo.py",
        "workspace_relative_path": "src/foo.py"
      }
    ]
  }
}
```

Validation:

- `path` must be absolute.
- For a run with `working_directory_snapshot`, resolved file paths must stay inside that root.
- The path must be a file. Directories are not accepted as `selected_files`.
- The relay stores path metadata only; it does not read the file contents.
- Limit selected files to a small bounded count, recommended 20.

### Browse API

Add a workspace/run scoped metadata endpoint that lists files and directories without reading file contents.

Recommended endpoints:

- `GET /api/workspaces/{workspace_id}/browse-files?path=/absolute/path`
- optionally `GET /api/runs/{run_id}/browse-files?path=/absolute/path` when steering an old run whose workspace snapshot may differ from the current workspace

Response:

```json
{
  "root": "/absolute/workspace",
  "path": "/absolute/workspace/src",
  "parent": "/absolute/workspace",
  "entries": [
    {"name": "app.py", "path": "/absolute/workspace/src/app.py", "workspace_relative_path": "src/app.py", "kind": "file"},
    {"name": "pkg", "path": "/absolute/workspace/src/pkg", "workspace_relative_path": "src/pkg", "kind": "directory"}
  ],
  "truncated": false
}
```

Safety:

- Reject rootless workspaces.
- Reject non-absolute paths.
- Resolve symlinks and reject escapes outside the root.
- Do not include file contents.

## Local conversation MCP tools

The relay already stores local conversations, runs, events, plans, and artifacts. Expose a minimal MCP surface so Workspace Agents can use those local conversations as context.

Tools:

### `list_local_conversations`

Inputs:

- `workspace_id?: number`
- `agent_id?: number`
- `limit?: number` clamped, default 50
- `include_archived?: boolean` default false

Output: public conversation fields and bounded latest run summary.

### `create_local_conversation`

Inputs:

- `name: string`
- `conversation_key?: string`
- `agent_id?: number`
- `workspace_id?: number | null`

Output: created public conversation.

Rules:

- Local state only; never dispatches a Workspace Agent trigger.
- If `conversation_key` is omitted, the store generates one.
- Defaults may reuse current agent/workspace settings.

### `read_local_conversation`

Inputs:

- exactly one of `conversation_id` or `conversation_key`
- `run_limit?: number` clamped
- `event_limit_per_run?: number` clamped
- `include_artifacts?: boolean` default false

Output:

- public conversation fields
- recent runs
- each run's plan and bounded event excerpts
- artifact metadata by default; artifact content only if explicitly enabled and bounded

Rules:

- Read-only.
- Does not read filesystem paths.
- Does not return access tokens, dashboard auth tokens, `.env` contents, or arbitrary local files.

### Optional `start_local_run`

This is useful if a Workspace Agent wants to create a local placeholder turn in another relay conversation without triggering a remote Workspace Agent.

Inputs:

- `conversation_id` or `conversation_key`
- `input_markdown: string`

Output: local run with generated `request_id` and `conversation_key`.

Rules:

- Local state only; no trigger API call.
- Existing `record_plan` / `record_progress` / `record_result` may then fill that run if the agent has its `request_id`.

## Skills registry

The relay builds a skills metadata index from `SKILL.md` files.

Candidate roots:

- global/user:
  - `~/.agents/skills/<name>/SKILL.md`
  - `~/.codex/skills/<name>/SKILL.md`
  - `~/.codex/skills/.system/<name>/SKILL.md`
- project:
  - `<working_directory>/.agents/skills/<name>/SKILL.md`
  - `<working_directory>/.codex/skills/<name>/SKILL.md`

Metadata:

```json
{
  "name": "diagnose",
  "description": "Disciplined diagnosis loop...",
  "path": "/Users/envvar/.agents/skills/diagnose/SKILL.md",
  "scope": "global"
}
```

Rules:

- Parse only frontmatter metadata.
- Do not render `SKILL.md` body into the trigger.
- Skip invalid or missing metadata.
- Project skills should sort before global skills.
- Use deterministic sorting and bounded count/description length.
- A selected or relevant skill tells the Agent where to read the full `SKILL.md`; it does not replace skill reading.

Injection:

- Initial first run of a local conversation: include `available_skills`.
- Later queued/new runs in the same conversation: omit `available_skills`.
- Steer/answer triggers: omit `available_skills`.

## Tests

Backend:

- trigger payload renders selected files and omits file contents
- initial trigger renders skills metadata
- continuation/steer/answer omit skills metadata
- selected file validation rejects relative paths, directories, symlink/root escapes, and paths outside the run workspace
- file browse returns file/directory metadata and never content
- local conversation MCP tools create/list/read bounded local store data
- MCP tools do not expose token values

Frontend:

- composer keeps existing Enter / Shift+Enter / Cmd+Enter behavior
- selecting a file adds a visible reference and structured `selected_files`
- queue/steer sends preserve selected file context for the correct message
- build passes

Protocol sync:

- `src/workspace_agent_relay_mcp/trigger.py`
- `src/workspace_agent_relay_mcp/server.py` `MCP_INSTRUCTIONS`
- `docs/agent-instructions.md`

These must agree on relay mode, local context references, skills first-run prelude, and local conversation tools.
