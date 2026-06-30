You are executing `relay-architecture-hardening/W1`.

Use the codex-conductor skill.

Identity:
- workflow_slug: relay-architecture-hardening
- workflow_label: Relay Architecture Hardening
- run_id: 20260629
- project_label: workspace-agent-relay-mcp
- task_id: W1
- task_label: Implementation
- role: worker
- assigned_session_title: Relay Architecture Hardening: Worker - Implementation [W1]
- assigned_handoff: /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/W1.md
- assigned_branch: launcher worktree branch, preferably based on origin/main
- assigned_worktree: confirm actual cwd

Goal:
Implement the architecture hardening items from the review: RunLifecycle/status machine, API/TS contract cleanup, composer queue controller/test seam, trigger dispatch adapter, tool-trace validation, and workspace directory adapter locality where applicable, with actual tests and verification.

First action:
Call `create_goal` with objective `relay-architecture-hardening: W1 - implement architecture hardening`.

Read:
- /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/AGENTS.md
- /Users/envvar/work/repos/poke/AGENTS.md
- /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/workflow-state.md
- /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/tasks/W1-implementation.md

Task mode:
implementation-slice

Project Constraints Capsule:
- Backend uses `.venv/bin/python`.
- Frontend uses `pnpm` in `frontend/`.
- Store changes require tests.
- Relay protocol wording changes must keep `src/workspace_agent_relay_mcp/trigger.py`, `src/workspace_agent_relay_mcp/server.py`, and `docs/agent-instructions.md` synchronized.
- Current controller checkout is dirty; your implementation should be in your assigned worktree and must not revert unrelated work.

Verification tier:
unit-or-component plus frontend build.

Allowed writes:
- `src/`
- `frontend/src/`
- `tests/`
- `frontend/tests/`
- `docs/agent-instructions.md` only when protocol text changes
- `docs/superpowers/specs/` only if a protocol/schema design update is needed
- assigned handoff only

Forbidden:
- Do not edit workflow files except your assigned handoff.
- Do not stage workflow control-plane files in product commits.
- Do not push, open PR, merge, deploy, restart services, or touch production.
- Do not read secrets, `.env`, sqlite DBs, keychains, SSH keys, or credential stores.
- Do not use `git reset --hard` or destructive cleanup.

Bootstrap:
1. Confirm `pwd`, repo root, branch, and `git status`.
2. If dependencies are already available, do not reinstall.
3. If dependency install is required, follow lockfiles and AGENTS guidance.

Required proof:
- `.venv/bin/python -m pytest tests/ -q`
- focused frontend node tests including any new queue/controller tests
- `cd frontend && pnpm run build`

Skip:
- live ChatGPT callback E2E
- launchd/cloudflared restarts
- browser/manual UI unless needed to prove a changed frontend interaction

Budget:
- One coherent implementation slice.
- Stop and hand off if you need secrets, production mutation, or cross-repo changes.

Worktree/commit:
- Confirm actual cwd/repo/branch before edits.
- Create scoped product commits after verification if feasible.
- Keep product commits free of workflow-state, registry, prompt, and handoff files.
- Do not push.

Handoff:
Write the required handoff to the assigned path with the exact fields from the task file.
