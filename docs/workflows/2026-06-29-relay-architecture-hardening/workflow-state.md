# Relay Architecture Hardening Workflow

## Identity

workflow_slug: relay-architecture-hardening
workflow_label: Relay Architecture Hardening
run_id: 20260629
project_label: workspace-agent-relay-mcp
controller_thread: 019f1344-e0d1-7391-87d9-1ef24709fc96
canonical_control_plane: /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening

## Orchestration Brief

goal: Complete the backend/frontend architecture optimizations identified by the deep review, with real implementation and verification.
deliverables:
- Product code changes implementing the review recommendations.
- Focused tests for lifecycle, API contract, composer/queue behavior, trigger dispatch, trace validation, and workspace directory adapter behavior where changed.
- Verification evidence from backend pytest, focused frontend node tests, and frontend build.
- Compact handoffs from execution and verification sessions.
in_scope:
- Run lifecycle/status-machine hardening.
- Dashboard REST/SSE and TS type contract cleanup.
- Composer/queue/steer dispatch controller extraction or equivalent testable seam.
- Trigger dispatch adapter/lifecycle ownership.
- Tool trace payload validation.
- Workspace directory adapter locality cleanup if it remains relevant after current code state is reconciled.
- Protocol text consistency across `trigger.py`, `server.py`, and `docs/agent-instructions.md` when protocol wording changes.
out_of_scope:
- Production deploys, live tunnel changes, or launchd restarts unless explicitly authorized later.
- GitHub PR creation unless explicitly authorized later.
- Reverting unrelated local dirty work in the controller checkout.
acceptance_criteria:
- Backend focused tests cover lifecycle edge cases: `needs_user` must not be cleared by late progress before an operator answer; live callbacks after `trigger_failed` produce coherent run status/display semantics.
- `POST /api/conversations/:id/runs` rejects blank `input_markdown` consistently with steer.
- Frontend statuses are typed or contract-tested enough to avoid silent drift from backend status constants.
- Composer queue/flush/send race behavior has focused tests covering rapid normal send, queue flush, and explicit steer/answer.
- Trigger dispatch has an explicit module/seam with exception handling and app lifecycle ownership or documented bounded lifecycle behavior.
- Tool trace payload validation rejects wrong summary/error/started_at/duration types.
- Required verification passes: `.venv/bin/python -m pytest tests/ -q`; `cd frontend && pnpm run build`; focused frontend node tests added/updated by the worker.
constraints:
- Current controller checkout is dirty and `main` is ahead of `origin/main`; do not revert or stage those unowned product changes from the controller.
- Product implementation must run in an execution session, preferably an isolated worktree from `origin/main`, unless the controller explicitly changes shape.
- Store changes require tests.
- Any relay protocol wording change must keep `trigger.py`, `server.py`, and `docs/agent-instructions.md` in sync.
known_artifacts:
- Previous review report: /var/folders/vn/4x0ljfzs2bjff2j7w_m60__h0000gn/T//architecture-review-20260629-202248.html
- Repo instructions: /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/AGENTS.md
- Host conductor profile: /Users/envvar/.config/codex-conductor/host.md
open_questions:
- None for implementation/publish. GitHub PR remains unauthorized/not requested.
recommended_first_harness: one implementation worker in isolated worktree from `origin/main`, then one verifier/reviewer session or controller verification from the worker handoff.
long_run_mode: none

## Project Constraints Capsule

source_files:
- AGENTS.md
- ../AGENTS.md
- /Users/envvar/.config/codex-conductor/host.md
capability_mode: managed
package_manager:
- Backend: Python venv at `.venv`; use `.venv/bin/python`.
- Frontend: `pnpm` in `frontend/`; package manager declared as `pnpm@11.9.0`.
verification_tiers:
- tier: unit-or-component
  use_when: backend store/API/lifecycle changes
  commands:
  - `.venv/bin/python -m pytest tests/ -q`
  skip: live end-to-end ChatGPT callback
- tier: unit-or-component
  use_when: frontend pure model/controller tests
  commands:
  - `node --test frontend/tests/*.test.mjs`
  skip: browser/manual UI unless a change requires it
- tier: integration-runtime
  use_when: any frontend product code or TS API type changes
  commands:
  - `cd frontend && pnpm run build`
  skip: `pnpm dev` unless visual/runtime verification is required
worktree_bootstrap:
- use_when: isolated implementation worker
  steps:
  - Confirm `pwd`, repo root, branch/ref, and `git status`.
  - Do not copy `.env`, sqlite DBs, or heavyweight runtime artifacts.
  - Use existing `.venv`/frontend deps if available in the created worktree; otherwise follow lockfiles and repo instructions before installing.
  forbidden:
  - `git reset --hard`
  - destructive deletes
  - production/tunnel/launchd mutation
lifecycle:
- commits: implementation worker may create scoped product commits after required proof; control-plane files must not be included in product commits.
- branches: use `codex/relay-architecture-hardening-*` or launcher-created worktree branch.
- issues_prs: not authorized.
control_plane_publication:
- default: keep high-frequency workflow files local/unpublished.
- delivery: verified product commits only; raw controller trace excluded.
forbidden_commands:
- `git reset --hard`
- `git checkout --` for unowned files
- direct production deploy/restart
worker_prompt_must_include:
- Read AGENTS instructions.
- Preserve unowned local work; do not stage controller workflow files into product commits.
- Provide compact handoff with proof commands and decisive results.

## Workflow Shape

task_mode: implementation-slice followed by evidence-session
dependency_shape: parallel audit fanout, then serialized or bounded-parallel fixes
reason: Write fixes may collide on shared types/status behavior, but report closure audits are independent and should run in parallel.
complexity_budget:
- max_active_write_sessions: 1
- max_active_audit_sessions: 3
- max_active_verifier_sessions: 1
- controller_context_budget: one minimal worker readback after launch, then handoff/proof pointers only
- shrink_trigger: if worker handoff is missing but recent status shows closing/progressing, ask one closeout instead of launching replacement
communication_rule: workers write compact handoff to `handoffs/`; controller verifies from files/commands, not chat claims.
state_source_of_truth:
- workflow-state.md
- session-registry.md
- tasks/*.md
- handoffs/*.md
delivery_policy: product implementation is committed and published to `origin/main`; raw controller trace remains excluded.

## Program Backlog

current:
- Final closeout complete; no unblocked backlog remains.
completed:
- Deep architecture review and HTML report.
- W1: Implement architecture hardening in isolated product worktree.
- V1: Controller verification of W1 commit and proof commands.
- D1: Cherry-pick W1 onto local `main` lineage, resolve integration conflict with prior rapid-send commits, verify, and push fast-forward to `origin/main`.
- A-BE/A-FE/A-CM: Parallel closure auditors mapped R1-R8 and found the remaining R2 backend SSE stream blocker.
- W2: Fixed the R2 SSE stream route regression in commit `6d701225deab`, verified it, and pushed it to `origin/main`.
- V-FINAL: Independently verified `origin/main` commit `6d701225deab`; R1-R9 closed; full backend pytest, frontend node tests, frontend build, and diff check passed.
pending:
- None.
blocked:
- None.
next:
- None.
launch_condition:
- No further launch needed.

## Evidence Rules

- Worker self-report is not proof.
- Proof requires command outputs, committed diff pointers, runtime evidence, or handoff with exact commands.
- Controller must rerun or independently inspect required verification before declaring complete.
- If a verification command cannot run, record why and lower the completion claim.

## Stop Lines

- Stop before push, PR, merge, deploy, launchd restart, tunnel mutation, or production state change.
- Push to `origin/main` was completed only after confirming prior user authorization and a fast-forward remote.
- Stop before staging/committing dirty files from the controller checkout unless a later instruction explicitly assigns that lifecycle work.
- Stop if implementation needs secrets, `.env`, SQLite data, or external account state.

## Controller Checkpoint

current_wave: reopened-closure-audit
completed:
- Capability discovery found Codex thread tools and Goal support.
- Host profile read.
- Repo AGENTS and parent AGENTS read.
- Dirty checkout noted: local main ahead of origin/main plus uncommitted product changes.
- W1 launched in isolated worktree and confirmed branch `codex/relay-architecture-hardening-w1`.
- W1 completed product commit `f8527d6 feat(relay): 强化运行状态与队列分发`.
- Controller reran required verification in W1 worktree and confirmed pass.
- Controller created integration worktree `/Users/envvar/.codex/worktrees/relay-hardening-main-publish`, cherry-picked W1 onto local `main` lineage as `ccf982d`, resolved `RelayPage.tsx` conflict by combining composer-controller decisions with optimistic message UX, reran verification, and pushed `ccf982d` to `origin/main`.
- Process miss recorded: controller previously closed the workflow without report-wide closure matrix or independent per-item audit.
- Controller created `closure-matrix.md` and tasks A-BE/A-FE/A-CM.
- Controller launched A-BE/A-FE/A-CM in parallel worktrees from `origin/main`.
- A-CM closed R7/R8; A-FE closed frontend R2/R3/R9 portion; A-BE closed R1/R4/R5/R6 but found R2 backend SSE route regression.
- Controller launched W2 implementation worker for R2 SSE import/test fix.
- W2 committed `6d701225deab fix(api): 修复运行流缺失异步导入`, controller independently reran full backend pytest, frontend node tests, frontend build, and diff check, then pushed it to `origin/main`.
- V-FINAL independently verified clean detached `origin/main` at `6d701225deab`: R1-R9 closed; `173 passed, 3 warnings`; `node --test` 12 passed; frontend build passed; `git diff --check` passed.
pending:
- None.
decisions:
- Use isolated implementation worktree from `origin/main` to avoid touching unowned dirty controller checkout.
- Keep control-plane files local and out of product commits.
- Replace separate V1 session with controller-run evidence because proof was deterministic commands on a clean W1 commit.
- Publish via a separate integration worktree to avoid staging or reverting dirty files in the controller checkout.
- Prior W1/D1 are evidence only; they no longer close the full workflow until auditors confirm every report row.
- Parallel fanout is required for independent audit surfaces; write fixes remain bounded because shared status/API contracts may conflict.
- Product delivery is complete at `origin/main` commit `6d701225deab`; raw workflow/control-plane trace remains local and unpublished.
proof_verified:
- `git status -sb` in W1 worktree: clean on `codex/relay-architecture-hardening-w1`.
- `git show --stat --name-status f8527d6`: product files only; no workflow control-plane files.
- `git diff --check f8527d6^..f8527d6`: pass.
- `.venv/bin/python -m pytest tests/ -q`: 172 passed, 3 warnings.
- `node --test frontend/tests/*.test.mjs`: 9 passed.
- `cd frontend && pnpm run build`: pass, existing chunk-size warning only.
- Integration worktree `git diff --check`: pass.
- Integration worktree `PYTHONPATH=$PWD/src /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/ -q`: 172 passed, 3 warnings.
- Integration worktree `node --test frontend/tests/*.test.mjs`: 12 passed.
- Integration worktree `cd frontend && pnpm run build`: pass, existing chunk-size warning only.
- `git push origin HEAD:main`: fast-forwarded `origin/main` from `31b4f0b` to `ccf982d`.
- W2 worktree `git diff --check`: pass.
- W2 worktree `PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`: 173 passed, 3 warnings.
- W2 worktree `node --test frontend/tests/*.test.mjs`: 12 passed.
- W2 worktree `cd frontend && pnpm run build`: pass, existing chunk-size warning only.
- `git push origin HEAD:main`: fast-forwarded `origin/main` from `ccf982d` to `6d70122`.
- V-FINAL worktree `HEAD == origin/main == 6d701225deabc76e3235ce0c97db89c7404a71d9`.
- V-FINAL `PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider`: 173 passed, 3 warnings.
- V-FINAL `node --test frontend/tests/*.test.mjs`: 12 passed.
- V-FINAL `cd frontend && pnpm run build`: pass, existing chunk-size warning only.
- V-FINAL `git diff --check`: pass.
next_actions:
- None. Do not create PR, deploy, restart services, or mutate production state without explicit authorization.
