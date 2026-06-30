# A-BE Backend / Protocol Audit Handoff

task_id: A-BE
thread_id: 019f13b1-3f1a-7b23-94cb-501efe72c822
session_title: Relay Hardening: Auditor - Backend [A-BE]
cwd: /Users/envvar/.codex/worktrees/7cd3/workspace-agent-relay-mcp
repo_root: /Users/envvar/.codex/worktrees/7cd3/workspace-agent-relay-mcp
branch: detached HEAD
head: ccf982d588fa
origin_main: ccf982d588fa
git_status: clean (`## HEAD (no branch)`)
commit: none - read-only audit; only this handoff was written
status: needs-review

## Conclusion

Backend closure is mostly supported by current `origin/main`, but I do not mark the backend side fully closed because R2 has a concrete API route regression: `/api/runs/{run_id}/stream` raises `NameError: name 'asyncio' is not defined` when exercised, because `runs.py` uses `asyncio.wait_for` / `asyncio.TimeoutError` without importing `asyncio`.

Verdicts:

| Item | Verdict | Summary |
| --- | --- | --- |
| R1 | closed | Backend lifecycle seam exists and relevant store transitions/tests cover the reported boundaries. |
| R2 backend half | needs-fix | Blank create/steer validation and async dispatch semantics are fixed, but SSE stream route is broken by missing `asyncio` import and lacks a route smoke test. |
| R4 | closed | App-owned `TriggerDispatcher` owns task registry, cleanup, drain/cancel, redacted exception persistence; cleanup/error are tested and drain was directly probed. |
| R5 | closed | `/internal/tool-trace` validates optional field types and stores normalized trace payloads; minor test gap noted for `ok` non-bool / bool duration type variants. |
| R6 | closed | Workspace directory picker/list/browse logic is in `workspace_directories.py`; HTTP route maps adapter errors/status; tests cover route seam behavior. |

## Environment / Scope Proof

- Confirmed actual cwd/repo/root/ref/status:
  - `pwd` -> `/Users/envvar/.codex/worktrees/7cd3/workspace-agent-relay-mcp`
  - `git rev-parse --show-toplevel` -> same path
  - `git rev-parse --short=12 HEAD` -> `ccf982d588fa`
  - `git rev-parse --short=12 origin/main` -> `ccf982d588fa`
  - `git status --short --branch` -> `## HEAD (no branch)`
- Read required artifacts:
  - `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/AGENTS.md`
  - `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/closure-matrix.md`
  - `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/tasks/A-BE.md`
  - `/var/folders/vn/4x0ljfzs2bjff2j7w_m60__h0000gn/T/architecture-review-20260629-202248.html`
- No product code edits, commits, push, PR, deploy, launchd/tunnel changes, or destructive git operations.

## R1 - RunLifecycle state-machine seam

Verdict: closed.

Code evidence:

- `src/workspace_agent_relay_mcp/run_lifecycle.py:5-24` defines literal `RunStatus`, `TriggerStatus`, and `ResultStatus`.
- `src/workspace_agent_relay_mcp/run_lifecycle.py:26-37` centralizes `TERMINAL_STATUSES`, `USER_REPLY_STATUSES`, `VALID_RESULT_STATUSES`, and `TRIGGER_MUTABLE_RUN_STATUSES`.
- `src/workspace_agent_relay_mcp/run_lifecycle.py:39-74` defines transition helpers:
  - `after_trigger_sent`
  - `after_trigger_result`
  - `after_plan`
  - `after_progress`
  - `after_tool_trace`
  - `after_user_question`
  - `after_operator_steer`
- `src/workspace_agent_relay_mcp/store/relay_store.py:12-24` imports lifecycle constants/helpers into the store.
- `src/workspace_agent_relay_mcp/store/relay_store.py:880-898` routes trigger-sent mutation through `after_trigger_sent`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:900-953` routes operator steer through `after_operator_steer`; `src/workspace_agent_relay_mcp/run_lifecycle.py:73-74` leaves user-reply statuses via `"sent"`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:994-1036` routes `record_plan` through `after_plan`; `src/workspace_agent_relay_mcp/run_lifecycle.py:51-54` clears stale `trigger_failed` display to `accepted`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1038-1070` routes trigger result through `after_trigger_result`; `src/workspace_agent_relay_mcp/run_lifecycle.py:43-48` only mutates draft/sent statuses.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1135-1194` routes `record_progress` through `after_progress`; `src/workspace_agent_relay_mcp/run_lifecycle.py:57-60` preserves user-reply statuses instead of clearing `needs_user`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1196-1243` routes `record_tool_trace` through `after_tool_trace`; `src/workspace_agent_relay_mcp/run_lifecycle.py:63-66` moves `trigger_failed` to `waiting`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1268-1296` routes `ask_user` through `after_user_question`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1298-1346` validates agent result status with `VALID_RESULT_STATUSES`; terminal result status is the callback payload and is not an uncontrolled arbitrary string.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1072-1086` rejects callbacks once `run["status"] in TERMINAL_STATUSES`.

Test evidence:

- `tests/test_relay_store.py:531-576` covers terminal run rejecting late progress/question/result without reopening.
- `tests/test_relay_store.py:648-697` covers terminal callback rejection and conversation mismatch precedence.
- `tests/test_relay_store.py:700-740` covers late trigger-result metadata not reopening terminal run.
- `tests/test_relay_store.py:930-954` covers `record_result` rejecting system-only `superseded`.
- `tests/test_relay_store.py:1178-1227` covers steering a `needs_user` run as operator answer on same request.
- `tests/test_relay_store.py:1229-1267` covers late progress not clearing `needs_user` until operator answer.
- `tests/test_relay_store.py:1270-1331` covers late callbacks after `trigger_failed`: `record_plan` moves to `accepted`; tool trace moves to `waiting`.
- `tests/test_web_api.py:828-895` covers API steer answering `ask_user` on the same run and dispatching answer wording.
- `tests/test_web_api.py:1096-1149` covers non-terminal `trigger_failed` accepting plan/progress callbacks and advancing out of stale failure display.

Test/proof command:

```bash
PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/test_relay_store.py tests/test_web_api.py tests/test_tool_trace.py -q -p no:cacheprovider
```

Result: `98 passed, 1 warning in 41.91s`.

Notes / test gaps:

- `record_result` and `dismiss_run` still write terminal statuses directly (`relay_store.py:1342-1343`, `relay_store.py:1368-1369`), but `record_result` is constrained by `VALID_RESULT_STATUSES` and `dismiss_run` is operator/system-only. I do not consider this a closure blocker for the reported lifecycle bug.
- Frontend status contract is owned by A-FE; backend evidence above confirms the backend half.

## R2 - API / TS contract, backend half

Verdict: needs-fix.

Closed backend evidence:

- `src/workspace_agent_relay_mcp/api/routes/runs.py:122-124` rejects blank create-run `input_markdown` with 400.
- `src/workspace_agent_relay_mcp/api/routes/runs.py:210-212` rejects blank steer `input_markdown` with 400.
- `tests/test_web_api.py:579-593` covers blank create rejection, no run creation, and no trigger call.
- `src/workspace_agent_relay_mcp/api/routes/runs.py:149-162` marks the run `sent`, schedules background dispatch, and returns immediately with the local run.
- `src/workspace_agent_relay_mcp/api/routes/runs.py:31-56` submits trigger work to `request.app.state.trigger_dispatcher` rather than doing synchronous trigger handling in route.
- `tests/test_web_api.py:621-650` proves create-run returns before a blocking trigger response and later records accepted trigger metadata.
- `tests/test_web_api.py:685-895` covers steer route semantics: same run/request, targeted run support, no-active-run 409, and answer-to-ask_user mode.
- `frontend/src/api/client.ts:226-248` has no stale 502/sync-trigger fallback branch for create-run; it accepts the returned run object.
- `frontend/src/api/client.ts:256-283` only falls back to create on steer 409; there is no 502 branch.

Blocking counterevidence:

- `src/workspace_agent_relay_mcp/api/routes/runs.py:88-90` uses `asyncio.wait_for` and `asyncio.TimeoutError` in the SSE stream generator.
- `src/workspace_agent_relay_mcp/api/routes/runs.py:1-20` imports `json`, `sqlite3`, `Any`, Starlette types, and local modules, but does not import `asyncio`.
- Targeted route proof failed:

```bash
PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from starlette.testclient import TestClient
from workspace_agent_relay_mcp import server
from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore

with TemporaryDirectory() as d:
    root = Path(d)
    server.config = RelayConfig(
        state_dir=root / 'state',
        auth_token='local-secret',
        default_agent_token='agent-token',
        default_trigger_url='https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger',
    )
    server.store = RelayStore(server.config.database_path)
    agent = server.store.upsert_agent(name='default', trigger_url=server.config.default_trigger_url, token_ref='env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN')
    conv = server.store.create_conversation(agent_id=agent['id'], name='Sherlog', conversation_key='research:sherlog')
    run = server.store.create_run(agent_id=agent['id'], conversation_id=conv['id'], conversation_key='research:sherlog', input_markdown='task', idempotency_key='idem', request_id='run_1')
    app = server.build_http_app()
    try:
        with TestClient(app) as client:
            with client.stream('GET', f"/api/runs/{run['id']}/stream", headers={'Authorization': 'Bearer local-secret'}) as response:
                print('status', response.status_code)
                for index, line in enumerate(response.iter_lines()):
                    print('line', index, line[:80] if isinstance(line, str) else line)
                    if index > 2:
                        break
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc))
PY
```

Result:

```text
NameError: name 'asyncio' is not defined
```

Minimal fix scope:

- Add `import asyncio` to `src/workspace_agent_relay_mcp/api/routes/runs.py`.
- Add a focused backend route test that opens `/api/runs/{run_id}/stream` and asserts the initial SSE event is emitted without exception. Likely file: `tests/test_web_api.py`.

## R4 - TriggerDispatch adapter lifecycle

Verdict: closed.

Code evidence:

- `src/workspace_agent_relay_mcp/trigger_dispatch.py:14-21` defines app-owned `TriggerDispatcher` and documents bounded shutdown behavior: wait briefly; no persisted replay across process death.
- `src/workspace_agent_relay_mcp/trigger_dispatch.py:23-30` owns the task registry and exposes `active_count`.
- `src/workspace_agent_relay_mcp/trigger_dispatch.py:32-74` owns trigger execution and persistence of trigger result.
- `src/workspace_agent_relay_mcp/trigger_dispatch.py:53-67` catches unexpected exceptions, redacts the access token with `redact_secret`, logs, and persists `trigger_http_status=0` plus `trigger_error`.
- `src/workspace_agent_relay_mcp/trigger_dispatch.py:76-90` schedules tasks and removes completed tasks in a done callback.
- `src/workspace_agent_relay_mcp/trigger_dispatch.py:92-107` drains pending tasks with timeout and cancels still-pending tasks.
- `src/workspace_agent_relay_mcp/app.py:76-84` instantiates one dispatcher and drains it in app lifespan shutdown.
- `src/workspace_agent_relay_mcp/app.py:106-108` attaches the app-owned trigger client, trigger dispatcher, and event bus to `app.state`.
- `src/workspace_agent_relay_mcp/api/routes/runs.py:31-56` route code submits dispatch jobs to `request.app.state.trigger_dispatcher`.

Test/proof evidence:

- `tests/test_web_api.py:596-618` covers completed dispatch tasks being cleaned from the registry.
- `tests/test_web_api.py:621-650` covers route returning before trigger result and later recording accepted trigger metadata.
- `tests/test_web_api.py:1063-1093` covers dispatcher exception handling: route initially returns sent, later `trigger_failed`, persists redacted exception text, and does not expose `agent-token`.
- Direct drain/cancel proof:

```bash
PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python - <<'PY'
import asyncio
from workspace_agent_relay_mcp.trigger_dispatch import TriggerDispatcher

async def main():
    dispatcher = TriggerDispatcher(store=object())
    async def never_finishes():
        await asyncio.Event().wait()
    task = dispatcher.schedule(never_finishes())
    await asyncio.sleep(0)
    before = dispatcher.active_count
    await dispatcher.drain(timeout=0.01)
    await asyncio.sleep(0)
    print(f'before={before} after={dispatcher.active_count} cancelled={task.cancelled()} done={task.done()}')

asyncio.run(main())
PY
```

Result:

```text
before=1 after=0 cancelled=True done=True
```

Test gap:

- Existing committed tests do not directly exercise lifespan shutdown drain/cancel; the adapter has documented bounded lifecycle and the direct proof above confirms behavior.

## R5 - Tool trace payload/event payload boundary

Verdict: closed.

Code evidence:

- `src/workspace_agent_relay_mcp/api/routes/internal.py:20-24` requires non-blank strings for required fields.
- `src/workspace_agent_relay_mcp/api/routes/internal.py:27-31` validates `args_summary` / `result_summary` as object or null.
- `src/workspace_agent_relay_mcp/api/routes/internal.py:56-58` validates `started_at` as string or null.
- `src/workspace_agent_relay_mcp/api/routes/internal.py:60-62` validates `error` as string or null.
- `src/workspace_agent_relay_mcp/api/routes/internal.py:64-68` validates `duration_ms` as non-bool number and non-negative.
- `src/workspace_agent_relay_mcp/api/routes/internal.py:70-72` validates `ok` as boolean when present.
- `src/workspace_agent_relay_mcp/api/routes/internal.py:74-85` passes normalized values into `store.record_tool_trace`, defaulting omitted `ok` to `True`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1196-1243` stores a normalized trace event as `event_type="progress"` with payload keys `trace`, `tool`, `title`, `args_summary`, `result_summary`, `started_at`, `duration_ms`, `ok`, `error`, and `turn_ord`.
- `src/workspace_agent_relay_mcp/store/relay_store.py:1245-1266` formats compact one-line trace markdown while preserving full error in payload.

Test evidence:

- `tests/test_tool_trace.py:82-120` covers stored progress event, trace marker, summaries, duration, `ok`, error null, and no unintended status mutation for non-`trigger_failed`.
- `tests/test_tool_trace.py:122-147` covers failure markdown truncation and full error preservation.
- `tests/test_tool_trace.py:149-170` covers trace not mutating plan steps.
- `tests/test_tool_trace.py:281-301` covers authenticated `/internal/tool-trace` creating a progress event with trace payload.
- `tests/test_tool_trace.py:303-339` covers internal bearer auth wrong/missing/disabled.
- `tests/test_tool_trace.py:342-381` covers unknown request id and missing/malformed required input.
- `tests/test_tool_trace.py:384-411` covers invalid optional payload types for summaries, `started_at`, negative duration, and `error`; it also asserts no event was created on invalid input.

Test/proof command:

```bash
PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/test_relay_store.py tests/test_web_api.py tests/test_tool_trace.py -q -p no:cacheprovider
```

Result: `98 passed, 1 warning in 41.91s`.

Test gap:

- `internal.py:64-72` implements rejection for bool `duration_ms` and non-bool `ok`, but the current invalid-case table does not explicitly include those two variants. I do not mark this needs-fix because implementation evidence is exact and the broader invalid optional type path is tested.

## R6 - Workspace directory adapter locality

Verdict: closed.

Code evidence:

- `src/workspace_agent_relay_mcp/workspace_directories.py:12-17` normalizes picked directories and validates directory existence.
- `src/workspace_agent_relay_mcp/workspace_directories.py:19-21` derives workspace display name from selected directory.
- `src/workspace_agent_relay_mcp/workspace_directories.py:24-32` normalizes browse path and rejects non-absolute/non-directory paths.
- `src/workspace_agent_relay_mcp/workspace_directories.py:35-59` lists directory entries, parent/home metadata, and truncation.
- `src/workspace_agent_relay_mcp/workspace_directories.py:62-77` implements macOS picker behind adapter seam.
- `src/workspace_agent_relay_mcp/workspace_directories.py:80-102` implements Linux picker behind adapter seam.
- `src/workspace_agent_relay_mcp/workspace_directories.py:105-126` implements Windows picker behind adapter seam.
- `src/workspace_agent_relay_mcp/workspace_directories.py:129-134` dispatches platform picker by `sys.platform`.
- `src/workspace_agent_relay_mcp/api/routes/workspaces.py:10` imports adapter functions from `workspace_directories`.
- `src/workspace_agent_relay_mcp/api/routes/workspaces.py:20-32` route only runs `browse_directory` and maps `PermissionError`/`ValueError`/`OSError` to HTTP statuses.
- `src/workspace_agent_relay_mcp/api/routes/workspaces.py:34-46` route only runs `pick_directory`, maps adapter exceptions, and formats the HTTP response.

Test evidence:

- `tests/test_web_api.py:282-294` monkeypatches the route-level adapter seam for `pick_directory` and verifies selected path/name response.
- `tests/test_web_api.py:297-318` verifies browse endpoint lists only host directories, sorted, with path/parent/home/truncated fields.
- `tests/test_web_api.py:320-327` verifies browse endpoint maps non-absolute path to 400.

Test gap:

- Browse tests use a real temp filesystem rather than monkeypatching `browse_directory`; this still validates route+adapter behavior and status mapping. Picker route is mocked at the imported adapter seam.

## Proof Commands Run

1. Targeted backend/component suite:

```bash
PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/test_relay_store.py tests/test_web_api.py tests/test_tool_trace.py -q -p no:cacheprovider
```

Result: `98 passed, 1 warning in 41.91s`.

2. SSE stream route smoke proof:

Result: failed with `NameError: name 'asyncio' is not defined`; see R2.

3. Trigger dispatcher drain/cancel proof:

Result: `before=1 after=0 cancelled=True done=True`; see R4.

## Changed Files

- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/A-BE.md`

## Controller Updates

- Mark A-BE as complete but not all-closed.
- R2 backend half should be moved to `needs-fix`.
- Minimal fix should be a tiny backend patch: add `import asyncio` in `src/workspace_agent_relay_mcp/api/routes/runs.py` and add an SSE initial-event smoke test in `tests/test_web_api.py`.
- R1, R4, R5, R6 can be treated as backend-closed with the noted test gaps.

## Blockers / Decisions Needed

- No blocker for this audit.
- Controller decision: assign the R2 SSE route fix to a write-capable backend worker, or fold it into the final fix pass if one exists.

## Noise Events

- Initial `cat` of `codex-conductor/SKILL.md` was truncated by tool output; reran with `sed` ranges and read the complete file before proceeding.
- I ran one extra targeted SSE smoke proof beyond the requested three pytest files because the route code showed an unimported `asyncio` reference; this found the R2 needs-fix item.
- No product code was edited.

## Efficiency Notes

- Focused pytest command took 41.91s.
- The read-only audit used direct code/file evidence plus focused route probes; no thread transcript reads were needed.

## Tool Fit

- `rg`, `nl`, and focused pytest fit the audit well.
- `PYTHONDONTWRITEBYTECODE=1` avoided cache writes in the read-only worktree.

## Do Not Read Transcript Unless

- The handoff file is missing or contradicted by code.
- Controller needs to inspect the exact SSE smoke proof command beyond the copied command/result above.

## Remaining / Follow-up Work If Seen

- Fix R2 SSE route import/test gap.
- Consider adding direct tests for dispatcher lifespan drain/cancel and `tool-trace` `ok` / bool-duration invalid cases, but those are not blocking the current backend closure except where the controller wants stricter test completeness.
