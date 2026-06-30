# W1 - Implementation

## Objective

Implement the architecture hardening items identified in the review for `workspace-agent-relay-mcp`, with tests and a compact handoff.

## Task Mode

implementation-slice

## Verification Tier

unit-or-component plus frontend build.

## Read First

- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/AGENTS.md`
- `/Users/envvar/work/repos/poke/AGENTS.md`
- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/workflow-state.md`
- This task file.

## Starting Evidence From Review

Implement these in priority order:

1. RunLifecycle/status-machine seam.
   - Centralize backend run statuses and transition decisions enough to remove direct ad-hoc writes.
   - Add tests for `ask_user` then late `record_progress`: status must remain semantically paused until operator answer/steer.
   - Decide and implement coherent status behavior for live callbacks after `trigger_failed`; at minimum plan/progress/tool/result must not leave UI in a misleading stuck failure state.
2. API and TS contract hardening.
   - `create_run` must reject blank `input_markdown`, matching steer.
   - Frontend `Run` status/trigger status/nullability should be stricter or contract-tested.
   - Remove/update obsolete synchronous 502 trigger-failure client semantics if no longer true.
3. Composer/queue/steer controller seam.
   - Extract or otherwise isolate the send/queue/flush/steer decision state from `RelayPage` enough to test rapid send and queue flush behavior.
   - Add focused frontend node tests for rapid normal sends, queue flush, and explicit steer/answer behavior.
4. Trigger dispatch adapter/lifecycle.
   - Move route-local background dispatch logic into an explicit module or app-owned adapter.
   - Ensure exception redaction and task cleanup are tested or covered by focused API tests.
   - If full shutdown drain is overkill for this prototype, document and bound the lifecycle in code/tests.
5. Tool trace payload validation.
   - Validate `args_summary`/`result_summary` object-or-null, `started_at` string-or-null, `error` string-or-null, `duration_ms` number and non-negative.
   - Add API tests for invalid payloads.
6. Workspace directory adapter locality.
   - If current code still mixes route and OS adapter logic, split or localize it with focused tests.
   - Do not remove existing workspace directory UX.

## Allowed Writes

- Product code under `src/`, `frontend/src/`.
- Tests under `tests/`, `frontend/tests/`.
- Protocol docs under `docs/agent-instructions.md` only when protocol text changes.
- Specs under `docs/superpowers/specs/` only if a protocol/schema-level design update is needed.
- Assigned handoff: `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/W1.md`.

## Forbidden

- Do not edit controller workflow files other than the assigned handoff.
- Do not stage/commit workflow-state, registry, task prompts, or handoffs into product commits.
- Do not push, open PR, deploy, restart launchd services, touch tunnels, or read secrets.
- Do not revert unrelated dirty work in the controller checkout.

## Required Proof

Run and record decisive results:

- `.venv/bin/python -m pytest tests/ -q`
- Focused frontend node tests, including any new queue/controller tests.
- `cd frontend && pnpm run build`

If dependencies are missing in the worktree, follow repo lockfiles and AGENTS guidance.

## Commit Policy

Create scoped product commits after verification if the worktree is suitable. Use commit format `<type>(scope): <summary>` with a Chinese summary under 50 characters. Do not push.

## Handoff Required Shape

Write `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/W1.md` with:

- task_id
- thread_id
- session_title
- cwd
- branch
- commit or `none` with reason
- status: `complete`, `blocked`, or `needs-review`
- conclusion
- changed_files
- proof commands and short decisive results
- controller_updates
- blockers or decisions needed
- noise_events
- efficiency_notes
- tool_fit
- do_not_read_transcript_unless
- remaining_or_followup_work_if_seen

