# V-INT — Integration Verification Handoff

## Status

Integrated and verified in the controller checkout. No commit, push, PR, deploy, launchd restart, or tunnel mutation was performed.

## Integrated Scope

- W-CORE backend/docs/tests:
  - selected-file local context validation/storage/trigger rendering
  - workspace/run-scoped file browse APIs
  - `SKILL.md` metadata registry and first-run-only skills injection
  - local conversation MCP tools: `list_local_conversations`, `create_local_conversation`, `read_local_conversation`
  - synchronized protocol wording in `trigger.py`, `server.py` `MCP_INSTRUCTIONS`, and `docs/agent-instructions.md`
- W-FEFILE frontend/tests:
  - `@file` composer trigger/button
  - file picker/chips
  - selected-file context through create-run, steer, queued messages, and queue flush
  - frontend API/types for browse and local context
- Controller fix:
  - Restored missing pre-existing `frontend/src/components/SettingsSheet.tsx` from worker baseline after build exposed it as missing in the dirty controller checkout.
  - Added `Run.local_context` and optional selected-file `reason` to `frontend/src/api/types.ts` to align frontend types with backend run detail output.

## Proof Commands

```bash
.venv/bin/python -m pytest tests/ -q
```

Result: `190 passed, 3 warnings in 9.29s`.

```bash
node --test frontend/tests/*.test.mjs
```

Result: `16 passed, 0 failed`.

```bash
cd frontend && pnpm run build
```

Result: passed; Vite emitted existing chunk-size and plugin-timing warnings only, ending with `✓ built in 3.42s`.

```bash
git diff --check
```

Result: passed with no output.

## Browser Smoke

Used an isolated backend on `127.0.0.1:8899` with a temporary state dir and an isolated Vite dev server on `127.0.0.1:5181`; both were stopped after the smoke run and the temp state dir was removed.

Steps verified in the in-app browser:

- Dashboard loaded against the isolated backend.
- Draft composer rendered with the `Add file context` control.
- Typing trailing `@` opened the `@file` picker rooted at `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp`.
- Root entries included files and directories; selecting `AGENTS.md` closed the picker.
- A visible `AGENTS.md` file chip appeared.
- Textarea value became `检查 `, confirming the trailing `@` trigger was removed after selection.
- Browser console error log count: `0`.

## Protocol Sync Evidence

`rg` inspection confirmed:

- `protocol: local-agent-shell/v1` and `turn_mode` are present in `src/workspace_agent_relay_mcp/trigger.py`, `src/workspace_agent_relay_mcp/server.py`, `docs/agent-instructions.md`, and trigger tests.
- `selected_files` and `available_skills` rules are documented in `docs/agent-instructions.md`, represented by trigger rendering, and covered by backend tests.
- Local conversation MCP tools are documented in `server.py` and `docs/agent-instructions.md`, implemented in `server.py` / `store/relay_store.py`, and covered by MCP callback tests.

## Unresolved / Deferred

- No live ChatGPT Workspace Agent trigger was sent during verification.
- No commit, push, PR, deploy, launchd restart, or tunnel mutation was authorized or performed.
- The controller checkout still contains pre-existing dirty/staged files unrelated to this integration; do not stage or commit them without a separate ownership pass.

## Next Action

Controller can summarize verified delivery and stop at the lifecycle boundary. If the user asks to publish, first re-check `git status`, separate pre-existing dirty files from this work, then run focused verification again before staging/commit/push/PR.
