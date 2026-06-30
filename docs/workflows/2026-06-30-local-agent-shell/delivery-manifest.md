# Local Agent Shell Delivery Manifest

## Status

The feature is implemented and verified in the current checkout, but not published. The current git index contains pre-existing staged work, so do not commit the current index as-is.

Latest verification already run in this checkout:

- `.venv/bin/python -m pytest tests/ -q`: pass, `190 passed, 3 warnings`
- `node --test frontend/tests/*.test.mjs`: pass, `16 passed`
- `cd frontend && pnpm run build`: pass with existing Vite warnings only
- `git diff --check`: pass
- In-app browser smoke: pass for `@file` picker/chip behavior, recorded in `handoffs/V-INT.md`

## Feature-Owned Product Files

These files are part of the Local Agent Shell feature delivery:

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

Tests:

- `tests/test_local_context.py`
- `tests/test_skills_registry.py`
- `tests/test_trigger_payload.py`
- `tests/test_web_api.py`
- `tests/test_mcp_callbacks.py`
- `frontend/tests/composerController.test.mjs`
- `frontend/tests/queueModel.test.mjs`

Product docs/spec:

- `docs/agent-instructions.md`
- `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md`

## Workflow / Control-Plane Files

These are recovery and orchestration artifacts. They should remain local/private by default unless the user explicitly wants to publish a milestone archive:

- `docs/workflows/2026-06-30-local-agent-shell/workflow-state.md`
- `docs/workflows/2026-06-30-local-agent-shell/session-registry.md`
- `docs/workflows/2026-06-30-local-agent-shell/tasks/W-CORE.md`
- `docs/workflows/2026-06-30-local-agent-shell/tasks/W-FEFILE.md`
- `docs/workflows/2026-06-30-local-agent-shell/tasks/V-INT.md`
- `docs/workflows/2026-06-30-local-agent-shell/prompts/W-CORE.md`
- `docs/workflows/2026-06-30-local-agent-shell/prompts/W-FEFILE.md`
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md`
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-FEFILE.md`
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/V-INT.md`
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/controller-final.md`
- `docs/workflows/2026-06-30-local-agent-shell/delivery-manifest.md`

## Pre-Existing / Not Feature-Owned Staged Files

These files were already staged or dirty outside this feature scope. Do not include them blindly in a feature commit unless their ownership is separately confirmed:

- `docs/superpowers/specs/2026-06-29-draft-conversation-title-tool.md`
- `frontend/src/components/AddWorkspaceDialog.tsx`
- `frontend/src/components/RelaySidebar.tsx`
- `frontend/src/components/ThreadView.tsx`
- `frontend/src/features/relay/components/ThreadHeader.tsx`
- `frontend/src/lib/conversationKey.ts`

Some files have both pre-existing staged changes and feature-owned unstaged changes. Treat the index as unsafe for direct commit; publish from an explicit delivery set, not from `git commit` on the current staged state.

## Delivery Strategy When Authorized

Preferred safe route:

1. Create or switch to a clean delivery branch only after checking the current dirty state and confirming ownership.
2. Apply/copy the feature-owned final file set listed above onto that delivery branch.
3. Decide whether to omit workflow control-plane files or replace them with one compact milestone archive.
4. Run:

   ```bash
   .venv/bin/python -m pytest tests/ -q
   node --test frontend/tests/*.test.mjs
   cd frontend && pnpm run build
   git diff --check
   ```

5. Stage only the delivery set.
6. Commit with repository format, e.g. `feat(relay): 添加本地 Agent Shell 协议`.
7. Push / PR / deploy / restart only if explicitly authorized for that boundary.

## Current Scope Guard

Current implementation intentionally excludes:

- `@folder`
- `@diff`
- `@recent`
- `@terminal`
- `@selection`
- `@symbol`
- image channels
- memory flows
- broad tool-proactivity coaching

The only unsupported-entity grep hit is the protocol spec's non-goal line that explicitly excludes those entities.
