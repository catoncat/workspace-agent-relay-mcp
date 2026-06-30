# W-CORE — Backend protocol, skills, and local conversation MCP

## Objective

Implement the backend half of Local Agent Shell:

- local context protocol in trigger payloads
- selected-file backend validation and file browse metadata API
- skills metadata registry and first-conversation-run injection
- local conversation MCP tools
- synchronized protocol wording in backend/docs

Use the design spec at `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md`.

## Mode

implementation-slice

## Allowed writes

- `src/workspace_agent_relay_mcp/trigger.py`
- `src/workspace_agent_relay_mcp/server.py`
- `src/workspace_agent_relay_mcp/workspace_directories.py`
- `src/workspace_agent_relay_mcp/api/routes/workspaces.py`
- `src/workspace_agent_relay_mcp/api/routes/runs.py`
- `src/workspace_agent_relay_mcp/store/relay_store.py`
- new backend modules under `src/workspace_agent_relay_mcp/`
- `tests/`
- `docs/agent-instructions.md`
- `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md` if implementation evidence requires tightening the spec
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md`

Do not edit frontend files in this task.

## Required behavior

1. Add `protocol: local-agent-shell/v1` and `turn_mode` to trigger inputs.
2. Add local context rendering:
   - `selected_files` may appear on initial/continuation/steer/answer when supplied.
   - `available_skills` appears only on the first queued/new run of a local conversation.
   - no file contents or `SKILL.md` bodies are rendered.
3. Extend create-run and steer backend handling to accept structured local context with selected files.
4. Validate selected files:
   - absolute path only
   - must be a file
   - if `working_directory_snapshot` exists, resolved path must stay inside it
   - bounded count
   - store metadata only
5. Add workspace-scoped file metadata browsing:
   - list directories and files
   - root/path escape protection, including symlinks
   - no file content
6. Add a skills registry module:
   - scan global/user and project roots from the spec
   - parse frontmatter `name` and `description`
   - bounded deterministic output
   - project before global
   - invalid skills skipped safely
7. Add MCP tools for local conversations:
   - `list_local_conversations`
   - `create_local_conversation`
   - `read_local_conversation`
   - optional `start_local_run` only if it stays local-only and cleanly reuses existing callback tools
8. Sync protocol wording across:
   - `trigger.py`
   - `server.py` `MCP_INSTRUCTIONS`
   - `docs/agent-instructions.md`

## Required tests

Add focused tests proving:

- trigger payload includes selected file references and not file contents
- initial first run includes skills metadata; continuation/steer/answer do not
- skills registry parses fixture `SKILL.md` metadata and skips body sentinel
- selected-file validation rejects relative paths, directories, outside-root paths, and symlink escapes
- file browse lists file/directory metadata and rejects workspace/root escapes
- MCP local conversation tools create/list/read bounded data and do not expose secrets
- existing relay behavior remains intact

Run:

```bash
.venv/bin/python -m pytest tests/ -q
```

If time is tight, run focused tests first, but the handoff must state full-suite status.

## Handoff

Write `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md` with:

- changed files
- implementation summary
- exact proof commands/results
- known conflicts or integration notes for W-FEFILE
- any behavior deferred intentionally
- noise/efficiency notes
