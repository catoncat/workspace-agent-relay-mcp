# W2 SSE Stream Smoke Fix

## Objective

Fix the backend `needs-fix` found by A-BE: `/api/runs/{run_id}/stream` uses `asyncio.wait_for` / `asyncio.TimeoutError` but `src/workspace_agent_relay_mcp/api/routes/runs.py` does not import `asyncio`. Add a focused route smoke test so this cannot regress.

## Mode

implementation-slice.

## Allowed Writes

- `src/workspace_agent_relay_mcp/api/routes/runs.py`
- `tests/test_web_api.py`
- assigned handoff file

## Forbidden

- Frontend edits.
- Store/lifecycle/protocol/schema changes unless the focused test proves they are required.
- Dependency/root config changes.
- Commits containing workflow control-plane files.
- Push, PR, deploy, launchd/tunnel changes, destructive git operations.

## Required Work

1. Add the missing `asyncio` import in `runs.py`.
2. Add a focused backend test that exercises `/api/runs/{run_id}/stream` enough to prove the route does not raise the missing import failure and emits/opens the expected initial SSE response.
3. Run focused verification:
   - `PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/test_web_api.py -q -p no:cacheprovider`
   - If cheap, also run `PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/test_relay_store.py tests/test_web_api.py tests/test_tool_trace.py -q -p no:cacheprovider`
   - `git diff --check`
4. Commit the product fix with format `<type>(scope): <summary>`.

## Handoff

Write `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/W2.md` with:

- task_id, thread_id, cwd, branch, commit
- changed files
- exact proof commands and decisive results
- whether R2 backend `needs-fix` is resolved
- any blockers/noise/tool fit
