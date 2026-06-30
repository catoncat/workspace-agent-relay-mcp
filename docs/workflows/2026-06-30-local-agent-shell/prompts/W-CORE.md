You are executing `local-agent-shell/W-CORE`.

Use the `codex-conductor` skill.

Identity:
- workflow_slug: local-agent-shell
- workflow_label: Local Agent Shell
- run_id: 20260630
- project_label: workspace-agent-relay-mcp
- task_id: W-CORE
- task_label: Backend protocol and MCP
- role: worker
- assigned_session_title: Local Agent Shell: Worker - Backend Core [W-CORE]
- assigned_handoff: docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md

Goal:
Implement backend protocol, selected-file validation/browse, skills first-turn prelude, and local conversation MCP tools for the Local Agent Shell workflow.

First action:
Call `create_goal` with this objective.

Read:
- AGENTS.md
- docs/workflows/2026-06-30-local-agent-shell/workflow-state.md
- docs/workflows/2026-06-30-local-agent-shell/tasks/W-CORE.md
- docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md

Project constraints:
- Preserve unowned existing work. Do not revert files you did not change.
- The starting checkout may include dirty/staged changes inherited from the controller. Treat them as baseline unless they are directly in your assigned files.
- Do not edit frontend files.
- Do not read `.env`, sqlite data, credentials, private keys, or unrelated user secrets.
- Do not push, open PRs, merge, deploy, restart launchd, or touch production.

Allowed writes:
Only the paths listed in `tasks/W-CORE.md`.

Verification:
- Focused backend tests as you develop.
- Required final: `.venv/bin/python -m pytest tests/ -q`

Handoff:
Write `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-CORE.md` with changed files, proof commands/results, integration notes, deferred items, noise/efficiency notes, and tool fit.

Stop when verified or genuinely blocked. Do not mark your Goal complete unless the task is implemented and verified.
