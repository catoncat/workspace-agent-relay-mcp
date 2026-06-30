# Controller Final Handoff — Local Agent Shell

## Status

Implementation, integration, and verification are complete up to the repository lifecycle boundary.

No commit, push, PR, deploy, launchd restart, tunnel mutation, dependency change, or production mutation was performed. Those actions remain authorization-gated by repository rules and the workflow stop lines.

## Requirement Audit

| Requirement from objective | Evidence in current state | Status |
| --- | --- | --- |
| Use a controller/orchestration workflow, not ad-hoc single-thread execution | `workflow-state.md`, `session-registry.md`, task prompts, worker handoffs, V-INT handoff | satisfied |
| Implement first useful context primitive: `@file` | `frontend/src/features/relay/components/ThreadComposer.tsx`, `frontend/src/api/client.ts`, `frontend/src/features/relay/queueModel.ts`, `frontend/tests/*.test.mjs`, browser smoke | satisfied |
| Do not invent unsupported entities like `@folder`, `@diff`, broad context objects | Design spec and protocol only define selected files and skills metadata/local conversations; workflow `out_of_scope` records excluded entities | satisfied |
| Add MCP tools for local conversation create/list/read, modeled after Codex thread tools | `src/workspace_agent_relay_mcp/server.py`, `src/workspace_agent_relay_mcp/store/relay_store.py`, `tests/test_mcp_callbacks.py` | satisfied |
| Treat multi-agent as multi-local-conversation; local relay store supplies content because remote cannot fetch it | Local conversation MCP tools read relay-stored conversations/runs/events/artifacts; `docs/agent-instructions.md` documents local-state-only behavior | satisfied |
| Implement skills spec and inject global/project `SKILL.md` metadata at conversation start only | `src/workspace_agent_relay_mcp/skills_registry.py`, `src/workspace_agent_relay_mcp/trigger.py`, `tests/test_skills_registry.py`, `tests/test_trigger_payload.py`, `tests/test_web_api.py` | satisfied |
| Do not repeat skills descriptions every turn | Trigger tests and web API tests assert continuations/steers/answers do not include `available_skills` | satisfied |
| Provide clean prompt protocol/spec instead of over-instructing the remote agent | `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md`, synchronized `trigger.py`, `server.py`, `docs/agent-instructions.md` | satisfied |
| Skip image, memory, and broad tool-proactivity work | Workflow `out_of_scope` and implemented files have no image/memory/tool-proactivity feature work | satisfied |
| Verify before delivery | Backend pytest, frontend node tests, frontend build, diff check, and browser smoke are recorded in V-INT | satisfied |
| Publish/release | Not performed because push/PR/deploy/restart are explicitly authorization-gated | gated |

## Verified Proof

Latest controller verification after this handoff was written:

- `.venv/bin/python -m pytest tests/ -q`: `190 passed, 3 warnings in 3.40s`
- `node --test frontend/tests/*.test.mjs`: `16 passed, 0 failed`
- `cd frontend && pnpm run build`: passed with existing Vite warnings only, ending with `✓ built in 771ms`
- `git diff --check`: passed with no output

Additional browser/runtime smoke is recorded in `handoffs/V-INT.md`:

- In-app browser smoke: `@` opens `@file` picker; selecting `AGENTS.md` creates a visible chip; console errors `0`

## Changed Product Surfaces

Backend:

- `src/workspace_agent_relay_mcp/local_context.py`
- `src/workspace_agent_relay_mcp/skills_registry.py`
- `src/workspace_agent_relay_mcp/workspace_directories.py`
- `src/workspace_agent_relay_mcp/api/routes/workspaces.py`
- `src/workspace_agent_relay_mcp/api/routes/runs.py`
- `src/workspace_agent_relay_mcp/trigger.py`
- `src/workspace_agent_relay_mcp/server.py`
- `src/workspace_agent_relay_mcp/store/relay_store.py`

Frontend:

- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/relay/components/ThreadComposer.tsx`
- `frontend/src/features/relay/composerController.ts`
- `frontend/src/features/relay/queueModel.ts`
- `frontend/src/features/relay/hooks.ts`
- `frontend/src/pages/RelayPage.tsx`

Tests/docs:

- `tests/test_local_context.py`
- `tests/test_skills_registry.py`
- `tests/test_trigger_payload.py`
- `tests/test_web_api.py`
- `tests/test_mcp_callbacks.py`
- `frontend/tests/composerController.test.mjs`
- `frontend/tests/queueModel.test.mjs`
- `docs/agent-instructions.md`
- `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md`

## Session Closeout

- W-CORE thread `019f14bd-12a1-79f0-8e75-cbd6bc839068`: integrated, verified, unpinned, archived.
- W-FEFILE thread `019f14bd-3284-7af1-8bc8-74f651f3c3f2`: integrated, verified, unpinned, archived.
- V-INT: controller-run verification handoff written.

## Remaining / Gated Work

Only lifecycle publication remains. Before commit/push/PR/deploy/restart:

1. Re-check `git status --short --branch`.
2. Separate pre-existing staged/dirty files from this feature's owned changes.
3. Decide whether workflow control-plane files should remain local/private, be excluded, or be compressed into one public milestone archive.
4. Rerun focused verification on the exact staged/delivery set.
5. Only then stage, commit, push, PR, deploy, or restart if explicitly authorized.

## Process Notes

- Controller directly copied worker outputs into the dirty controller checkout for integration. This was a practical integration exception after worker handoffs completed; product changes were verified afterward.
- The checkout already had unrelated staged/dirty files before this workflow. Do not stage all files blindly.
- The current active Goal should remain active until the user authorizes or explicitly defers publication, because the original objective included “发布”.
