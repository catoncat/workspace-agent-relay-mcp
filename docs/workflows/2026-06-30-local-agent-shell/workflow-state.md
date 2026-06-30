# Local Agent Shell Workflow

## Identity

workflow_slug: local-agent-shell
workflow_label: Local Agent Shell
run_id: 20260630
project_label: workspace-agent-relay-mcp
controller_thread: 019f149c-a6c9-7ce1-9b11-740c2e2cb8c3
canonical_control_plane: /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-30-local-agent-shell

## Orchestration Brief

goal: Turn the relay into a local Codex-style Workspace Agent shell by adding explicit local-context protocol and tools: `@file`, local conversation MCP tools, and skills discovery/injection.

deliverables:
- `@file` composer selection that sends structured local file mentions to the backend and into the trigger protocol.
- MCP tools for creating/listing/reading local relay conversations so "multi-agent" can be modeled as local conversations whose stored content can be supplied back to a remote Workspace Agent.
- A local skills registry/spec that discovers global and project skills by `SKILL.md` metadata and injects the skill descriptions only on the first turn of a conversation.
- A compact prompt protocol that exposes selected files, available skills, and related local conversations as entities, without over-prescriptive behavior guidance.
- Focused backend and frontend tests, plus final backend pytest and frontend build evidence.

in_scope:
- `src/`, `frontend/src/`, `tests/`, `frontend/tests/`, `docs/agent-instructions.md`, and design specs under `docs/superpowers/specs/`.
- Local file selection only: explicit `@file` path mentions.
- Local conversation creation/read/list MCP tools backed by this relay's SQLite store.
- Skills metadata registry and first-conversation-turn trigger injection.
- Workspace orientation only as protocol/context assembly that includes skills and selected local entities; no broad behavioral "tool proactive" coaching.

out_of_scope:
- `@folder`, `@diff`, `@recent`, `@terminal`, `@selection`, `@symbol`, or other imagined context objects.
- Native Workspace Agent-to-Agent `@` behavior or remote ChatGPT conversation retrieval.
- Image/artifact generation channels.
- Memory review/persistence flows.
- Production deploys, tunnel/launchd restarts, push/PR/merge, dependency upgrades, or secret handling.

acceptance_criteria:
- `@file` UI has a discoverable picker, inserts/removes visible file chips, preserves plain text editing, and sends structured mentions with absolute paths scoped to the active workspace when possible.
- Backend validates selected file mentions without reading file contents by default; trigger input represents them as protocol entities and tells the agent to open them with local tools when useful.
- MCP exposes minimal local conversation tools with safe outputs: create/list/read conversation data from relay storage, bounded by local store and bearer/OAuth MCP auth already in place.
- Skills registry scans agreed global and project skill roots, extracts only metadata needed for selection/injection, handles missing/invalid `SKILL.md` safely, and avoids prompt bloat.
- Skills descriptions are injected only for a newly created conversation's first run; continuations/steers do not repeat the full skills prelude.
- Protocol wording is synchronized across `trigger.py`, `server.py` `MCP_INSTRUCTIONS`, and `docs/agent-instructions.md` when changed.
- Focused tests cover backend validation/store/MCP/trigger behavior and frontend composer behavior.
- Final checks pass: `.venv/bin/python -m pytest tests/ -q`; `cd frontend && pnpm run build`; relevant frontend node tests if added/changed.

constraints:
- The controller checkout is dirty, including staged product changes owned by prior work. Do not revert, stage, commit, or overwrite unowned dirty files from the controller.
- Treat the current working tree as the authoritative local state for design, but use isolated execution sessions/worktrees for product implementation.
- Store changes require tests.
- Public protocol/schema/type changes require backend and frontend contract alignment.
- Follow the repository rule: no spec-less major protocol changes.
- Principle: 如无必要，不增实体. Entities exist only when they carry explicit local context or recovery value.

known_artifacts:
- Repo instructions: /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/AGENTS.md
- Current pasted user discussion: /Users/envvar/.codex/attachments/478e558c-4fb9-49ba-ac22-4875e912ec50/pasted-text.txt
- Prior completed workflow, unrelated but useful for project profile: /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/workflow-state.md

open_questions:
- None blocking design/exploration. Implementation must stop before push/PR/deploy.

recommended_first_harness: controller-owned control plane plus parallel read-only explorers; then one or more isolated implementation sessions with disjoint write scopes after the protocol shape is fixed.
long_run_mode: none

## Project Constraints Capsule

source_files:
- AGENTS.md
- docs/workflows/2026-06-29-relay-architecture-hardening/workflow-state.md

capability_mode: managed

package_manager:
- Backend: Python venv at `.venv`; use `.venv/bin/python`.
- Frontend: `pnpm` in `frontend/`; lockfile `frontend/pnpm-lock.yaml`.

verification_tiers:
- tier: docs-only
  use_when: workflow/spec/control-plane updates
  commands:
  - inspect changed Markdown
  skip: backend/frontend runtime checks unless product files changed
- tier: unit-or-component
  use_when: backend store/API/MCP/trigger changes
  commands:
  - `.venv/bin/python -m pytest tests/ -q`
  skip: live ChatGPT callback
- tier: unit-or-component
  use_when: frontend model/controller tests
  commands:
  - `node --test frontend/tests/*.test.mjs`
  skip: browser manual checks unless UI behavior cannot be covered
- tier: integration-runtime
  use_when: frontend product code or TS API type changes
  commands:
  - `cd frontend && pnpm run build`
  skip: `pnpm dev` unless visual/runtime proof is required

worktree_bootstrap:
- use_when: isolated implementation worker
  steps:
  - Confirm `pwd`, repo root, branch/ref, and `git status`.
  - If starting from the controller working tree, preserve existing dirty baseline and do not revert unrelated files.
  - Do not copy or read `.env`, sqlite DBs, or heavyweight runtime artifacts.
  - Use existing venv/frontend dependencies when available; otherwise follow lockfiles and repo scripts.
  forbidden:
  - `git reset --hard`
  - destructive deletes
  - production/tunnel/launchd mutation

lifecycle:
- commits: not required in first implementation wave; if a worker commits, keep commits scoped and exclude raw control-plane files.
- branches: use Codex launcher worktrees or `codex/local-agent-shell-*`.
- issues_prs: not authorized.

control_plane_publication:
- default: workflow files are local recovery artifacts, not product delivery.
- delivery: verified product changes only; raw controller trace excluded unless user asks for an archive.

forbidden_commands:
- `git reset --hard`
- `git checkout --` for unowned files
- direct production deploy/restart
- reading `.env`, private keys, credentials, or unrelated user secrets

worker_prompt_must_include:
- Read AGENTS instructions.
- Preserve unowned local work; do not stage controller workflow files into product commits.
- Work only in assigned paths.
- Write compact handoff with proof commands and decisive results.

## Workflow Shape

task_mode: controller orchestration with read-only explorer fanout, followed by implementation-slice workers and a verifier/integration pass
dependency_shape: weak-dependency first, then bounded parallel
reason: `@file`, local conversation MCP tools, and skills/prompt protocol are separate evidence surfaces, but they join at trigger input and frontend/backend API contracts.

complexity_budget:
- max_active_explorers: 4
- max_active_write_sessions: 2 after protocol contracts are fixed
- max_active_verifier_sessions: 1
- controller_context_budget: consume compact explorer/worker outputs only; do not read long transcripts unless handoff/proof is missing or contradictory
- shrink_trigger: if implementation surfaces collapse into one shared contract, use a single worker instead of parallel workers

communication_rule: explorer outputs are evidence packets; durable implementation sessions must write handoffs under `handoffs/` or return the same shape.

state_source_of_truth:
- workflow-state.md
- session-registry.md
- tasks/*.md and prompts/*.md for launchable sessions
- handoffs/*.md for completed durable sessions

delivery_policy: stop before commit/push/PR/deploy unless the user explicitly authorizes lifecycle actions after verification.

## Program Backlog

current:
- Integrated implementation is verified in the controller checkout.
- W-CORE and W-FEFILE outputs are copied into the controller checkout and covered by backend, frontend, build, diff-check, and browser-smoke proof.
- Delivery is stopped at the lifecycle boundary: no commit, push, PR, deploy, launchd restart, or tunnel mutation is authorized.
- Worker sessions are reconciled, unpinned, and archived. Controller final handoff records the requirement audit and remaining publication gate.
- Delivery manifest now separates feature-owned product files, private workflow artifacts, and pre-existing staged/dirty files that must not be blindly committed.
completed:
- Controller thread titled for recovery.
- Repository instructions and existing workflow profile inspected.
- Current dirty/staged checkout recorded as a constraint.
- Four read-only explorer subagents launched.
- A-CONV returned: store can support local conversation management; MCP needs create/list/read tools and likely store detail helpers.
- A-FILE returned: composer is pure text today; existing directory browse is directories-only; `@file` needs workspace-scoped file metadata browse and mention payload plumbing.
- A-PROTO returned: core protocol should be envelope + local context entities + concise tool contract; current prompt has some behavior guidance that should move to tool/docs.
- A-SKILL returned: `build_trigger_input` initial branch is the correct prelude injection point; skills registry should scan metadata only and avoid continuation/steer repetition.
- W-CORE handoff copied to canonical control plane and integrated.
- W-FEFILE handoff copied to canonical control plane and integrated.
- Controller restored missing pre-existing `frontend/src/components/SettingsSheet.tsx` from worker baseline after `pnpm run build` exposed it as missing in the dirty checkout.
- Controller aligned frontend `Run` typing with backend `local_context` output.
- Controller verification passed:
  - `.venv/bin/python -m pytest tests/ -q`: `190 passed, 3 warnings in 9.29s`
  - `node --test frontend/tests/*.test.mjs`: `16 passed, 0 failed`
  - `cd frontend && pnpm run build`: passed with existing Vite warnings only
  - `git diff --check`: passed
- Controller browser smoke passed on isolated ports `8899`/`5181`: typing trailing `@` opened the `@file` picker, selecting `AGENTS.md` produced a visible chip, removed the trigger `@`, and produced zero browser console errors.
- V-INT handoff written at `docs/workflows/2026-06-30-local-agent-shell/handoffs/V-INT.md`.
- Controller final handoff written at `docs/workflows/2026-06-30-local-agent-shell/handoffs/controller-final.md`.
- W-CORE thread `019f14bd-12a1-79f0-8e75-cbd6bc839068` unpinned and archived.
- W-FEFILE thread `019f14bd-3284-7af1-8bc8-74f651f3c3f2` unpinned and archived.
- Delivery manifest written at `docs/workflows/2026-06-30-local-agent-shell/delivery-manifest.md`.
- Scope guard checked: no unsupported context entities were implemented; grep hit only the spec non-goal line excluding `@folder`, `@diff`, and similar imagined entities.
- `frontend/dist` is not tracked by git.
pending:
- User authorization for any lifecycle action such as staging, commit, push, PR, deploy, launchd restart, or tunnel mutation.
blocked:
- None.
next:
- Summarize verified delivery. If asked to publish, first separate pre-existing dirty/staged files from this work, then rerun focused verification before staging.
launch_condition:
- Launch implementation only after task files name exact allowed write paths and prompt protocol contract.

## Evidence Rules

- Worker/explorer claims are not proof by themselves; proof must cite files, commands, diffs, tests, or runtime readbacks.
- For trigger protocol changes, proof requires tests in `tests/test_trigger_payload.py` and synchronized text inspection.
- For MCP tools, proof requires MCP transport/callback tests or direct server tests.
- For frontend UI, proof requires focused frontend tests where practical and `pnpm run build`.
- If a verification command cannot run, record why and reduce completion claim.

## Stop Lines

- Stop before push, PR, merge, release, deployment, launchd restart, tunnel mutation, or production state changes.
- Stop before changing dependencies or lockfiles unless the implementation task explicitly needs it.
- Stop before reading secrets or private credential stores.
- Stop before staging or committing the existing dirty controller checkout.

## Controller Checkpoint

current_wave: integration-verified-lifecycle-gated
completed:
- Active Goal confirmed for the full workflow.
- `codex-conductor`, `proactive-work-amplifier`, and parallel-dispatch instructions loaded.
- Codex thread tools and subagent tools discovered.
- Controller title set to `Local Agent Shell: Controller - workflow`.
- Existing architecture-hardening workflow read as prior project profile; it is complete and not reused as this workflow's state.
- Current git state recorded: staged and unstaged product changes exist before this workflow; controller will not stage/revert them.
- Four read-only explorers launched:
  - A-FILE: @file composer/API inventory.
  - A-CONV: local conversation MCP inventory.
  - A-SKILL: skills registry and first-turn injection inventory.
  - A-PROTO: compact prompt protocol inventory.
- Added product spec `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md`.
- Added task/prompt files for W-CORE and W-FEFILE.
- Launched W-CORE and W-FEFILE as Codex worktree sessions from the current working-tree baseline; launcher returned pending worktree ids.
- Resolved W-CORE to thread `019f14bd-12a1-79f0-8e75-cbd6bc839068`, worktree `/Users/envvar/.codex/worktrees/bea2/workspace-agent-relay-mcp`.
- Resolved W-FEFILE to thread `019f14bd-3284-7af1-8bc8-74f651f3c3f2`, worktree `/Users/envvar/.codex/worktrees/83b3/workspace-agent-relay-mcp`.
- Pinned controller and active workers.
- W-FEFILE readback shows active TDD implementation: selected-file context tests were added first, red-light observed, and frontend model/API changes are being applied.
- W-FEFILE handoff copied to canonical control plane. Worker reported `node --test frontend/tests/*.test.mjs` pass (16/16) and `cd frontend && pnpm run build` pass; controller later reran these on the integrated checkout.
- W-CORE handoff copied to canonical control plane and integrated.
- W-FEFILE output integrated into the controller checkout.
- Controller verification completed, including backend pytest, frontend node tests, frontend build, diff-check, and isolated browser smoke.
- Worker sessions reconciled, unpinned, and archived after proof integration.
- Controller final handoff written with requirement audit and publication boundary.
- Fresh post-handoff verification completed:
  - `.venv/bin/python -m pytest tests/ -q`: `190 passed, 3 warnings in 3.40s`
  - `node --test frontend/tests/*.test.mjs`: `16 passed, 0 failed`
  - `cd frontend && pnpm run build`: passed with existing Vite warnings only
  - `git diff --check`: passed
- Delivery manifest written and current diff scope audited for unsupported entities and tracked build artifacts.
pending:
- Lifecycle authorization if the user wants commit/push/PR/deploy/restart.
decisions:
- Do not implement imagined context entities beyond `@file`.
- Treat multi-agent as local conversation composition, not native remote agent-to-agent `@`.
- Skills descriptions are a protocol prelude for the first conversation run, not a per-turn list-skills dependency.
- The product should expose clear entities/tools/protocol; avoid over-instructing the remote Agent's reasoning style.
proof_verified:
- `git status --short --branch` showed dirty/staged checkout before controller writes.
- `codex_app.list_projects` returned this repo project id `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp`.
- `.venv/bin/python -m pytest tests/ -q` passed: `190 passed, 3 warnings in 9.29s`.
- `node --test frontend/tests/*.test.mjs` passed: `16 passed, 0 failed`.
- `cd frontend && pnpm run build` passed with existing Vite warnings only.
- `git diff --check` passed with no output.
- In-app browser smoke passed for `@file` picker/chip behavior on isolated local servers.
- Controller final handoff: `docs/workflows/2026-06-30-local-agent-shell/handoffs/controller-final.md`.
- Fresh post-handoff verification: backend pytest, frontend node tests, frontend build, and diff check all passed.
- Delivery manifest: `docs/workflows/2026-06-30-local-agent-shell/delivery-manifest.md`.
next_actions:
- Stop before lifecycle actions unless explicitly authorized. If authorization arrives, separate pre-existing dirty/staged files from owned feature changes, rerun verification on the exact delivery set, then proceed with scoped stage/commit/push/PR or restart as requested.

## Noise / Efficiency Notes

- Existing dirty/staged product files make current checkout unsuitable for direct controller implementation.
- Parallel read-only explorers are used because the four evidence surfaces are independent and joinable; this avoids the controller inventing design details without code evidence.
