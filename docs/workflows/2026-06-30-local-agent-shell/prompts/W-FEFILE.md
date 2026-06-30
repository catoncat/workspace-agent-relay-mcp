You are executing `local-agent-shell/W-FEFILE`.

Use the `codex-conductor` skill.

Identity:
- workflow_slug: local-agent-shell
- workflow_label: Local Agent Shell
- run_id: 20260630
- project_label: workspace-agent-relay-mcp
- task_id: W-FEFILE
- task_label: Frontend @file
- role: worker
- assigned_session_title: Local Agent Shell: Worker - Frontend @file [W-FEFILE]
- assigned_handoff: docs/workflows/2026-06-30-local-agent-shell/handoffs/W-FEFILE.md

Goal:
Implement the frontend `@file` composer experience, preserving queue/steer behavior and sending structured selected-file context.

First action:
Call `create_goal` with this objective.

Read:
- AGENTS.md
- docs/workflows/2026-06-30-local-agent-shell/workflow-state.md
- docs/workflows/2026-06-30-local-agent-shell/tasks/W-FEFILE.md
- docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md

Project constraints:
- Preserve unowned existing work. Do not revert files you did not change.
- The starting checkout may include dirty/staged changes inherited from the controller. Treat them as baseline unless they are directly in your assigned files.
- Do not edit backend `src/` files.
- Do not read `.env`, sqlite data, credentials, private keys, or unrelated user secrets.
- Do not push, open PRs, merge, deploy, restart launchd, or touch production.

Allowed writes:
Only the paths listed in `tasks/W-FEFILE.md`.

Verification:
- Required final: `node --test frontend/tests/*.test.mjs`
- Required final: `cd frontend && pnpm run build`

Handoff:
Write `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-FEFILE.md` with changed files, proof commands/results, backend contract assumptions, integration risks, noise/efficiency notes, and tool fit.

Stop when verified or genuinely blocked. Do not mark your Goal complete unless the task is implemented and verified.
