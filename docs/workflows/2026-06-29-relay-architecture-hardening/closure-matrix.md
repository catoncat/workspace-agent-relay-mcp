# Architecture Review Closure Matrix

Source report: `/var/folders/vn/4x0ljfzs2bjff2j7w_m60__h0000gn/T/architecture-review-20260629-202248.html`

Controller rule: an item is closed only when an auditor/verifier maps it to code evidence and proof. A prior implementation commit is evidence, not closure by itself.

## Status Legend

- `open`: not yet audited or missing proof.
- `provisional`: implemented or claimed, waiting for independent audit.
- `closed`: auditor/verifier confirmed with code evidence and proof.
- `needs-fix`: audited and found incomplete.
- `deferred`: explicitly out of scope with reason.

## Matrix

| ID | Report Item | Required Closure Evidence | Current Evidence | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| R1 | RunLifecycle state-machine seam too shallow | Central lifecycle module or equivalent transition helper; store callbacks route status changes through it; tests cover `ask_user`, late progress, late callbacks after `trigger_failed`, terminal/user-reply boundaries; frontend status contract checked. | A-BE closed backend lifecycle with file/line evidence and `98 passed` targeted backend proof; A-FE closed frontend status contract. | A-BE + A-FE | closed |
| R2 | API / TS contract not hard enough | Literal `RunStatus` / `TriggerStatus`; nullable backend fields reflected in TS; route validation rejects blank create and steer consistently; stale sync-trigger 502 branches removed; backend tests and frontend build prove contract. | A-FE closed frontend half. A-BE found backend SSE regression. W2 fixed with commit `6d701225deab`, red/green SSE test, `test_web_api.py` route suite, three-file backend suite, and controller full pytest/node/build proof. V-FINAL verified the fix on `origin/main` at `6d701225deab` with full pytest/node/build/diff-check. | V-FINAL | closed |
| R3 | Composer / queue / steer controller too much in `RelayPage` | Pure controller/hook or equivalent testable seam; event-table tests for rapid send, flush, explicit steer/answer, failure restore; Page keeps side effects/composition only; integration with optimistic message commits verified. | A-FE closed with controller/test/RelayPage evidence and `node --test` + build proof. | A-FE | closed |
| R4 | TriggerDispatch adapter needs lifecycle ownership | Route submits jobs to adapter; app lifespan owns drain/cancel; exceptions redacted/persisted; task registry cleans completed tasks; tests cover dispatcher cleanup/shutdown/error behavior or documented bounded lifecycle. | A-BE closed with adapter/lifespan/test evidence and drain probe. | A-BE | closed |
| R5 | Tool trace payload/event payload boundary too wide | `/internal/tool-trace` rejects invalid optional types; summary object/null; started_at/error string/null; duration non-negative; store receives normalized payload; tests cover invalid types. | A-BE closed; noted minor optional future test variants for `ok` non-bool and bool duration. | A-BE | closed |
| R6 | Workspace directory adapter locality | OS picker/listing/path logic moved out of route; route handles HTTP validation/status mapping; tests mock adapter seam; UX unchanged. | A-BE closed with adapter and route-test evidence. | A-BE | closed |
| R7 | Protocol consistency across trigger/server/docs | Re-check `trigger.py`, `server.py`, `docs/agent-instructions.md`; if implementation changes protocol wording, all three are synced; no callback_token drift. | A-CM closed; active triad consistent and no callback_token matches. | A-CM | closed |
| R8 | Report completeness / no hidden findings | Every finding/evidence paragraph in HTML report mapped to one of R1-R7 or explicitly marked not actionable. | A-CM closed; no missing matrix rows. | A-CM | closed |
| R9 | End-to-end regression risk after cherry-pick onto main | Integration commit verified from clean `origin/main`; conflict resolution checked for loss of optimistic send or controller decisions; tests run on final published commit. | A-FE closed frontend conflict-resolution portion. V-FINAL verified final `origin/main` at `6d701225deab` after W2 with full backend pytest, frontend node tests, frontend build, and diff check. | V-FINAL | closed |

## Required Final Gate

Completed by V-FINAL at `origin/main` commit `6d701225deabc76e3235ce0c97db89c7404a71d9`:

1. A-BE and A-FE independently marked owned items closed or found a specific blocker.
2. A-CM confirmed R7/R8, including no unmapped report finding.
3. The only `needs-fix` item, R2 backend SSE stream, was assigned to W2, committed as `6d701225deab`, verified, and pushed to `origin/main`.
4. V-FINAL verified final `origin/main` with:
   - `PYTHONPATH=$PWD/src PYTHONDONTWRITEBYTECODE=1 /Users/envvar/work/repos/poke/workspace-agent-relay-mcp/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` -> `173 passed, 3 warnings`
   - `node --test frontend/tests/*.test.mjs` -> `12 passed`
   - `cd frontend && pnpm run build` -> pass, existing chunk warning only
   - `git diff --check` -> pass
