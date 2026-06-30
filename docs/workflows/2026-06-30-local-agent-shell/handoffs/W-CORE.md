# Worker Handoff

task_id: W-CORE
thread_id: 019f14bd-12a1-79f0-8e75-cbd6bc839068
session_title: Local Agent Shell: Worker - Backend Core [W-CORE]
cwd: /Users/envvar/.codex/worktrees/bea2/workspace-agent-relay-mcp
branch: detached HEAD
commit: none; lifecycle actions were not authorized
status: complete

## Conclusion

Backend core is implemented and verified. Trigger payloads now carry `protocol: local-agent-shell/v1`, `turn_mode`, selected-file reference metadata, and first-run skills metadata. Backend APIs validate/store selected-file metadata, expose workspace/run file metadata browsing, and MCP exposes bounded local conversation create/list/read tools.

## Changed Files

- `src/workspace_agent_relay_mcp/local_context.py`
- `src/workspace_agent_relay_mcp/skills_registry.py`
- `src/workspace_agent_relay_mcp/workspace_directories.py`
- `src/workspace_agent_relay_mcp/api/routes/workspaces.py`
- `src/workspace_agent_relay_mcp/api/routes/runs.py`
- `src/workspace_agent_relay_mcp/trigger.py`
- `src/workspace_agent_relay_mcp/server.py`
- `src/workspace_agent_relay_mcp/store/relay_store.py`
- `tests/test_local_context.py`
- `tests/test_skills_registry.py`
- `tests/test_trigger_payload.py`
- `tests/test_web_api.py`
- `tests/test_mcp_callbacks.py`
- `docs/agent-instructions.md`
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md`

Pre-existing dirty frontend files were not edited by this worker.

## Implementation Summary

- Added selected-file normalization/validation with absolute-path, file-only, workspace-root, symlink-escape, count, and metadata-only constraints.
- Added `runs.local_context_json` migration/storage and parsed `run.local_context` output.
- Added selected-file local context support for create-run and steer payloads.
- Added `GET /api/workspaces/{workspace_id}/browse-files` and `GET /api/runs/{run_id}/browse-files` metadata-only browsing.
- Added skills registry scanning project/global `SKILL.md` frontmatter only, with deterministic bounded output and project-before-global ordering.
- Added trigger rendering for local context and first-new-conversation available skills only.
- Added MCP tools: `list_local_conversations`, `create_local_conversation`, `read_local_conversation`.
- Synced protocol wording across `trigger.py`, `server.py` `MCP_INSTRUCTIONS`, and `docs/agent-instructions.md`.

## Proof Commands / Results

- `PYTHONPATH=src /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/test_trigger_payload.py tests/test_local_context.py tests/test_skills_registry.py tests/test_mcp_callbacks.py tests/test_web_api.py -q`
  - Result: pass, `82 passed, 1 warning`.
- `PYTHONPATH=src /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/ -q`
  - Result: pass, `190 passed, 3 warnings`.
- `.venv/bin/python -m pytest tests/ -q`
  - Result: pass, `190 passed, 3 warnings`.
- `git diff --check -- src/workspace_agent_relay_mcp docs/agent-instructions.md tests docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md`
  - Result: pass, no output.

## Integration Notes for W-FEFILE

- Create run accepts `local_context.selected_files` in `POST /api/conversations/{conversation_id}/runs`.
- Steer accepts `local_context.selected_files` in `POST /api/conversations/{conversation_id}/steer`.
- Successful run responses include `run.local_context.selected_files`; no file contents are stored or returned.
- The backend computes `workspace_relative_path` from the resolved file path under the workspace root. Frontend should not rely on preserving a user-supplied relative path.
- File browse endpoints return `{root, path, parent, entries, truncated}`; entries are directories first, then files, sorted by name.
- Browse and selected-file validation resolve symlinks and reject escapes outside the workspace root.
- Unknown `local_context` fields are rejected with 400.
- `available_skills` is trigger-only context; it is not returned by the browse APIs.

## Deferred Intentionally

- `start_local_run` MCP tool was omitted because it is optional in the spec and not needed for this backend slice.
- `related_local_conversations` trigger embedding was not implemented; local conversation content is available through MCP read/list/create tools instead.
- No frontend files, push/PR/deploy, launchd, or production state were touched.

## Noise / Efficiency Notes

- The worktree initially had no `.venv/`. A first attempt to symlink the main checkout venv and run the required exact command failed because that venv resolved the package from the main checkout and did not contain new modules. The worker then created an ignored local `.venv/` with `python3 -m venv .venv` and `pip install -e '.[dev]'`, after which the exact required command passed.
- The checkout already had dirty frontend/backend/control-plane files before this worker. The worker treated them as baseline and did not revert or stage anything.

## Tool Fit

- `apply_patch` fit source/test/doc edits.
- `pytest` with the project venv gave fast focused and full backend verification.
- The exact `.venv/bin/python` requirement needed local venv bootstrap in this isolated worktree.

## Controller Updates

- Mark W-CORE as complete after controller reconciliation.
- W-FEFILE can integrate against the new `local_context.selected_files` payload shape and file-browse endpoints.

## Do Not Read Transcript Unless

- Handoff proof contradicts test logs.
- W-FEFILE needs exact backend error wording beyond the notes above.
- Controller needs process forensics for the initial venv symlink failure.
