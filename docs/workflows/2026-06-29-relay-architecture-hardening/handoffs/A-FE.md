# A-FE Frontend / Composer Audit Handoff

task_id: A-FE
thread_id: 019f13b1-3f1a-7b23-94cb-502b34bec9d5
session_title: Relay Hardening: Auditor - Frontend [A-FE]
cwd: /Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp
repo_root: /Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp
branch: detached HEAD
audited_ref: ccf982d588fa442c3500dd4b3f1d918ff13e6856 (origin/main after fetch)
commit: none - read-only audit; wrote this handoff only
status: complete

## Conclusion

R2 frontend half: closed.
R3: closed.
R9 frontend conflict-resolution portion: closed.

The final `origin/main` frontend implementation has literal run/trigger status types, nullable run fields, the stale 502 client branch removed, a pure composer decision seam with focused tests, and RelayPage integration preserving optimistic messages, queue flush, explicit steer/answer, and the local dispatch guard.

## Item Verdicts

### R2 frontend half - closed

Evidence:
- Source report R2 asked for literal status types, nullable fields, removal of stale sync-trigger 502 behavior, and build/test proof: `/var/folders/vn/4x0ljfzs2bjff2j7w_m60__h0000gn/T/architecture-review-20260629-202248.html:116-133`.
- `RunStatus` is no longer a broad string: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/api/types.ts:60-78`.
- `TriggerStatus` is literal: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/api/types.ts:80-82`.
- `Run.status` and `Run.trigger_status` use those literals, and backend-nullable fields are typed nullable: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/api/types.ts:84-103`.
- Client `createRun` now accepts the background-dispatch response as a `Run` and has no 502 fallback branch: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/api/client.ts:226-247`; `rg` found no `502` handling in `frontend/src`.
- Client steer preserves only the expected 409 active-run race fallback to create a new turn: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/api/client.ts:250-282`.
- Backend create/steer blank validation is aligned: create rejects blank input at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/src/workspace_agent_relay_mcp/api/routes/runs.py:122-124`, steer rejects blank input at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/src/workspace_agent_relay_mcp/api/routes/runs.py:210-212`, and the create-route regression test is `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/tests/test_web_api.py:579-593`.

Test gaps:
- No generated/shared schema exists; this closure relies on TS literal/nullability plus backend tests and frontend build, which matches the closure matrix's minimum evidence.

### R3 - closed

Evidence:
- Source report R3 asked for moving composer/queue/steer decisions out of `RelayPage`, testing rapid send, flush, explicit steer/answer, and failure restore: `/var/folders/vn/4x0ljfzs2bjff2j7w_m60__h0000gn/T/architecture-review-20260629-202248.html:157-197`.
- Pure controller seam exists: `planComposerSend` decides ignore/queue/create/steer at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/features/relay/composerController.ts:20-51`; `planQueueFlush` decides ignore/wait/flush at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/features/relay/composerController.ts:53-81`; `restoreFailedFlush` is pure at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/features/relay/composerController.ts:83-88`.
- Rapid normal send/local dispatch pending test: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/tests/composerController.test.mjs:10-36`.
- Queue flush wait/dispatch test: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/tests/composerController.test.mjs:38-72`.
- Explicit steer/answer test: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/tests/composerController.test.mjs:74-87`.
- Failed flush restore test: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/tests/composerController.test.mjs:89-101`.
- Queue model remains pure and tested for FIFO, edit/remove, take-one, merge, and per-conversation isolation: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/features/relay/queueModel.ts:31-72` and `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/tests/queueModel.test.mjs:14-94`.
- RelayPage delegates send decisions to `planComposerSend` and only performs side effects/state updates after the plan: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:228-285`.
- RelayPage delegates flush decisions to `planQueueFlush`, clears the flushed queue, restores failed messages before newer queued input, and keeps the dispatch effect side-effectful only: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:340-393`.

Test gaps:
- There is no React component-level RelayPage race test; current proof is pure controller tests plus TypeScript build.
- The keybinding itself is not directly tested; code maps Enter to default queue/answer and Cmd/Ctrl+Enter to explicit steer at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/features/relay/components/ThreadComposer.tsx:78-92`.

### R9 frontend conflict-resolution portion - closed

Evidence:
- Audit worktree was `HEAD` detached at `ccf982d`, equal to fetched `origin/main`; no product files were edited.
- Final `RelayPage` imports both the composer controller and optimistic model, so the publish conflict resolution did not drop either side: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:13-17` and `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:27-32`.
- Local dispatch guard is retained: ref declaration at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:77-78`, guard cleanup at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:175-179`, guard input into `planComposerSend` at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:231-241`, and add/delete around create-run dispatch at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:258-266`.
- Optimistic messages are appended before dispatch and cleared on success/failure in normal/steer send: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:253-272`.
- Optimistic messages are appended/cleared around queue flush: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:365-382`.
- Optimistic messages are passed into the thread and rendered after persisted run details: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:510-514` and `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/components/ThreadView.tsx:181-183`.
- Optimistic model behavior is pure and tested: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/features/relay/optimisticMessageModel.ts:16-44` and `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/tests/optimisticMessageModel.test.mjs:14-58`.
- Explicit steer/answer path targets an active run id: selected/latest active run choice at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:135-148`, run id passed into the plan at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:231-241`, and steer mutation invoked with that run id at `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:256-257`.
- Queued-message immediate steer removes the queued item, calls explicit steer, and restores the item on failure: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/pages/RelayPage.tsx:310-331`.
- Question choice buttons send with explicit steer only while the run is `needs_user`: `/Users/envvar/.codex/worktrees/a0e7/workspace-agent-relay-mcp/frontend/src/components/ThreadView.tsx:725-737`.

Risk note:
- Queue flush still executes the create-run side effect directly from RelayPage after the pure `flush` decision. I did not mark this needs-fix because the decision seam now covers `localDispatchPending`, busy state, FIFO merge, and failure restore; the remaining direct call is side-effect execution, not untested dispatch policy.

## Proof Commands

- `git fetch origin main --prune`
  - Result: exit 0; fetched `origin/main`; audit worktree `HEAD` was `ccf982d`.
- `node --test frontend/tests/*.test.mjs`
  - Result: exit 0; 12 tests passed, 0 failed.
- `cd frontend && pnpm run build`
  - Result: exit 0; `tsc -b && vite build` succeeded; Vite emitted only the standard large-chunk warning.
- `rg -n "502|status === 502|trigger request failed" frontend/src/api frontend/src/features frontend/src/pages frontend/src/components frontend/tests`
  - Result: no matches.

## Changed Files

- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/A-FE.md` only.

## Blockers / Decisions Needed

- none.

## noise_events

- `cd frontend && pnpm run build` auto-installed `frontend/node_modules/` and generated `frontend/dist/` in the audit worktree because dependencies were absent. Both were ignored artifacts; I removed only those artifacts with `rm -rf -- frontend/dist frontend/node_modules`. Product/source files remained clean.
- Canonical checkout `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp` is dirty and behind `origin/main`; I did not use it for source audit. The audit source was the clean detached Codex worktree at fetched `origin/main`.

## efficiency_notes

- Focused read-only audit plus two frontend verification commands.
- Build install cost was avoidable if the worker worktree had dependencies; no retry was needed.

## tool_fit

- `rg`, `nl`, `git`, `node --test`, and `pnpm run build` fit the read-only audit well.
- `pnpm run build` had setup side effects due missing dependencies; cleanup was straightforward.

## do_not_read_transcript_unless

- Handoff/proof commands are insufficient for controller needs.
- Controller wants process forensics around the build artifact cleanup.

## remaining_or_followup_work_if_seen

- Optional future hardening: add a component-level RelayPage race test for flush-in-flight plus immediate manual send. Not required to close R3/R9 based on current matrix evidence.
