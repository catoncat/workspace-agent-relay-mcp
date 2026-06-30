# A-CM Handoff

task_id: A-CM
thread_id: 019f13b1-3f1a-7b23-94cb-5008c15ca5de
session_title: Relay Hardening: Auditor - Closure Matrix [A-CM]
cwd: /Users/envvar/.codex/worktrees/d4f5/workspace-agent-relay-mcp
repo_root: /Users/envvar/.codex/worktrees/d4f5/workspace-agent-relay-mcp
branch: detached HEAD at origin/main
commit: none; read-only audit, no product commit
status: complete

## Conclusion

R7: closed. The active protocol triad on current `origin/main` is mutually consistent for `request_id`, `conversation_key`, `relay_mcp`, optional `working_directory`, steer/current-turn semantics, `ask_user` pause/resume, and removal of per-run `callback_token`.

R8: closed. I re-read the complete HTML architecture report and found no actionable report finding outside R1-R7. R9 is a post-report delivery/regression gate, not a hidden report finding.

Missing matrix rows: none.

Protocol drift requiring fix: none.

## Worktree / Ref Proof

- Actual cwd: `/Users/envvar/.codex/worktrees/d4f5/workspace-agent-relay-mcp`.
- Repo root: `/Users/envvar/.codex/worktrees/d4f5/workspace-agent-relay-mcp`.
- Audited ref: `ccf982d588fa442c3500dd4b3f1d918ff13e6856`.
- `git status --short --branch` in audited worktree: `## HEAD (no branch)`.
- `git rev-parse origin/main`: `ccf982d588fa442c3500dd4b3f1d918ff13e6856`.
- `git ls-remote origin refs/heads/main`: `ccf982d588fa442c3500dd4b3f1d918ff13e6856 refs/heads/main`.
- Handoff target checkout `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp` is local `main` at `7e935c931bd3b374cffb1d78dc038f44eebbdfc8`, behind `origin/main` by one commit and already dirty/untracked before this audit. I used it only to read workflow files and write this assigned handoff.

## Report Section / Finding Mapping

| Report lines | Report content | Matrix coverage | Verdict |
| --- | --- | --- | --- |
| 27 | Review scope: backend API, RelayStore, MCP callback/tool-trace, trigger dispatch, frontend composer/queue/SSE/query, protocol docs. | Scope spans R1-R7; not a separate finding. | covered |
| 35 | Positive note: relay protocol mainline is clear; `request_id + conversation_key` seam and plan/progress/result store tests exist. | Non-actionable positive evidence; supports R7 context but needs no row. | covered |
| 39 | Main risk: run state machine is scattered; `late progress` clears `needs_user`; callbacks after `trigger_failed` leave failed display semantics. | R1. | covered |
| 43 | Highest leverage: explicit transition table, then align store/API/frontend/composer around one contract. | R1 primary; downstream R2/R3. | covered |
| 51 | Backend status set and frontend `runStatus` duplicate status constants. | R1. | covered |
| 52-53 | `record_progress` unconditionally writes `waiting`; dynamic proof that `ask_user -> needs_user` then progress becomes `waiting`. | R1. | covered |
| 54-55 | `record_plan` and `record_tool_trace` do not advance status after `trigger_failed`; dynamic proof that plan/tool trace succeed while run status remains failed. | R1. | covered |
| 56 | `create_run` accepts blank `input_markdown` while steer rejects blank input. | R2. | covered |
| 57 | TS `Run.status` / `trigger_status` too wide; nullable backend fields not nullable in TS. | R2. | covered |
| 58 | `RelayPage` owns send, queue, flush, steer, dispatch guard; depth/locality issue. | R3. | covered |
| 59 | Trigger background task registry lives in route closure; lifespan lacks drain/cancel. | R4. | covered |
| 66-88 | Section 1 recommends a RunLifecycle module/transition helper and tests for `needs_user`, `trigger_failed`, `steer`, terminal boundaries. | R1. | covered |
| 116-139 | Section 2 recommends harder API/TS contract: literal run/trigger statuses, nullable fields, route validation, stale sync-trigger 502 cleanup. | R2. | covered |
| 133, 138 | Section 2 also mentions `ToolTracePayload` and external sender/dashboard payload boundary. | R5 covers the tool-trace-specific boundary; R2 covers broader REST/TS contract. | covered |
| 159-180 | Section 3 recommends tested composer/queue/steer controller or hook; event-table coverage for rapid send, flush, explicit steer/answer. | R3. | covered |
| 203-219 | Section 4 recommends TriggerDispatch adapter with task registry, redaction/persistence, shutdown/drain/cancel behavior, debug counters. | R4. | covered |
| 239-255 | Section 5 recommends narrow tool-trace payload contract: summary object/null, error/started_at string/null, non-negative duration, normalized store payload. | R5. | covered |
| 274-290 | Section 6 recommends workspace directory adapter for path normalization, browse listing, platform picker, route HTTP mapping. | R6. | covered |
| 309-312 | Protocol consistency check: trigger/server/docs are aligned; implementation state-machine drift is the real mismatch. | R7 for text consistency; the implementation mismatch is already R1. | covered |
| 315-322 | Top recommendation: prioritize transition matrix; cover `ask_user`, answer steer, late progress, `trigger_failed` late callbacks, frontend status contract. | R1 primary; line 321 also reinforces R2-style contract proof. | covered |

## R7 Protocol Consistency Evidence

### `trigger.py`

- `src/workspace_agent_relay_mcp/trigger.py:46-59` builds the trigger header with `request_id`, `conversation_key`, `relay_mcp: workspace-agent-relay-mcp`, and optional nonblank `working_directory`.
- `src/workspace_agent_relay_mcp/trigger.py:77-82` tells the agent to treat `working_directory` as default cwd, verify it before filesystem/git operations, and explain if leaving it.
- `src/workspace_agent_relay_mcp/trigger.py:83-129` defines steer mode as same-turn guidance or answer on the same `request_id`; it instructs plan revision/skipped steps, not a new turn and not `record_result` for plan change.
- `src/workspace_agent_relay_mcp/trigger.py:95-103` frames `answer=True` as the operator's answer to `ask_user` and says to resume the current turn.
- `src/workspace_agent_relay_mcp/trigger.py:130-144` uses the same relay protocol reminder for continuation, with `record_plan -> bind_relay_run -> record_progress -> record_result` and the incoming `request_id`.
- `src/workspace_agent_relay_mcp/trigger.py:150-158` initial contract says one `request_id` scope, mid-turn correction uses plan/progress updates, `ask_user` pauses and is not finished, and `record_result` closes only when truly over.
- `src/workspace_agent_relay_mcp/trigger.py:185-195` posts `{conversation_key, input}` to the trigger endpoint; no per-run callback secret is included.

### `server.py`

- `src/workspace_agent_relay_mcp/server.py:58-70` MCP instructions align with the trigger text: record plan first, bind local ops, batch progress, result exactly once, steer reuses the same `request_id`, working directory is default cwd, `ask_user` pauses and answer resumes the same turn, and `blocked` is for external hard blockers.
- `src/workspace_agent_relay_mcp/server.py:116-135` `record_plan` takes `request_id` and `conversation_key` only for run identity.
- `src/workspace_agent_relay_mcp/server.py:152-175` `record_progress` takes `request_id` and `conversation_key` only; progress remains intermediate state.
- `src/workspace_agent_relay_mcp/server.py:191-209` `record_result` takes `request_id` and `conversation_key` only and constrains final statuses to `done | blocked | failed`.
- `src/workspace_agent_relay_mcp/server.py:224-237` `ask_user` takes `request_id` and `conversation_key` only and is for a human decision, not status updates.

### `docs/agent-instructions.md`

- `docs/agent-instructions.md:99-111` matches trigger/server working-directory semantics.
- `docs/agent-instructions.md:113-125` defines relay mode by `request_id`, `conversation_key`, and `relay_mcp: <YOUR_RELAY_MCP>`, with optional `working_directory`.
- `docs/agent-instructions.md:134-143` matches queue/new request versus steer/current-turn semantics and forbids treating steer itself as a separate result.
- `docs/agent-instructions.md:144-155` matches the required relay workflow: record plan, bind local ops with incoming `request_id` and optionally `conversation_key`, progress, ask only when blocked, result exactly once.
- `docs/agent-instructions.md:177-196` matches `ask_user` pause/resume semantics: same `request_id`, answer as steer, resume from blocked step, no new turn.
- `docs/agent-instructions.md:222-246` matches terminal-result semantics and forbids progress as final answer.

### Callback token removal

- `rg -n "callback_token" src/workspace_agent_relay_mcp/trigger.py src/workspace_agent_relay_mcp/server.py docs/agent-instructions.md` returned no matches (`exit=1`).
- Active tool signatures and trigger payloads use `request_id` + `conversation_key`; no active protocol text in the triad tells the agent to send or rotate a `callback_token`.
- Repo-wide historical specs/plans still mention `callback_token`, but they are older design/archive material, not the active trigger/server/agent-instructions triad covered by R7.

## Verdicts

| Item | Verdict | Reason |
| --- | --- | --- |
| R7 | closed | The active triad is synchronized and has no `callback_token` drift. The only server-side nuance is that `server.py` does not repeat the literal trigger header `relay_mcp` entry condition; it names the server and aligns all behavioral rules. This is not a contradiction or closure blocker. |
| R8 | closed | Every actionable report paragraph/list item maps to R1-R7. Positives, benefits, diagrams, and scope statements are evidence/motivation rather than separate closure items. |

## If Needs-Fix Were Required

No needs-fix item found. Minimal scope if a stricter reviewer wants `server.py` to mention the literal relay-mode header would be docs-only wording in:

- `src/workspace_agent_relay_mcp/server.py` `MCP_INSTRUCTIONS`
- `docs/agent-instructions.md`
- `src/workspace_agent_relay_mcp/trigger.py` only if the header semantics change

I do not recommend that as a blocker because the current text is not contradictory.

## Changed Files

- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/A-CM.md`

No product code, tests, root config, dependency files, launchd/tunnel state, commits, push, PR, deploy, or destructive git operation.

## Proof Commands / Readbacks

- `cat /Users/envvar/.agents/skills/codex-conductor/SKILL.md` plus ranged `sed` readback.
  - Result: codex-conductor protocol loaded; task treated as read-only `audit-track`.
- `pwd; git rev-parse --show-toplevel; git branch --show-current; git rev-parse HEAD; git rev-parse origin/main; git status --short --branch; git worktree list --porcelain`.
  - Result: audited worktree is detached `HEAD` at `ccf982d`, equal to local `origin/main`, clean.
- `git ls-remote origin refs/heads/main`.
  - Result: remote `main` is also `ccf982d588fa442c3500dd4b3f1d918ff13e6856`.
- `cat`/`nl -ba` of AGENTS, closure matrix, A-CM task, HTML report, `trigger.py`, `server.py`, and `docs/agent-instructions.md`.
  - Result: evidence captured in mapping and R7 sections above.
- `rg -n "callback_token" src/workspace_agent_relay_mcp/trigger.py src/workspace_agent_relay_mcp/server.py docs/agent-instructions.md; printf 'exit=%s\n' "$?"`.
  - Result: no matches, `exit=1`.

No test suite was run because the verification tier was docs/protocol read-only audit and the allowed write boundary was this handoff only.

## Controller Updates

- Mark R7 `closed`.
- Mark R8 `closed`.
- Do not add missing matrix rows for the HTML report.
- Keep R1-R6/R9 closure status dependent on their owner/verifier evidence; this audit only maps report completeness and protocol consistency.

## Blockers / Decisions Needed

- None.

## Noise Events

- The canonical handoff path is in the dirty local `main` checkout, while the audited source is the detached origin/main worktree. I kept reads/writes separated: source evidence from `/Users/envvar/.codex/worktrees/d4f5/workspace-agent-relay-mcp`, workflow/handoff files from `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp`.
- The first full `codex-conductor` skill read was truncated by tool output limits; I re-read it in line ranges before continuing.

## Efficiency Notes

- No subagent or new Codex session was launched. The audit was serial and read-only, with compact shell readbacks as proof.
- No dependency bootstrap or runtime verification was needed.

## Tool Fit

- `codex-conductor`: fit for Goal, read-only audit boundary, and handoff discipline.
- Shell `git`, `nl`, `cat`, and `rg`: fit for deterministic source/doc evidence.
- `apply_patch`: fit for creating the single allowed handoff file.

## Do Not Read Transcript Unless

- This handoff contradicts `origin/main` at `ccf982d`.
- The HTML report path changes or a newer report must be audited.
- A reviewer wants process forensics on the prior controller's closure claim.

## Remaining Or Follow-up Work If Seen

- None for A-CM.
