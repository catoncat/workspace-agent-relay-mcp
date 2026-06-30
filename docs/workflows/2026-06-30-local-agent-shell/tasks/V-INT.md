# V-INT — Integration and verification

## Objective

Integrate W-CORE and W-FEFILE outputs, resolve contract conflicts, and verify the Local Agent Shell feature set end to end within the local repository.

## Mode

evidence-session / review-fix-session if small conflicts need repair

## Launch condition

Launch after W-CORE and W-FEFILE both provide handoffs or one worker is classified unrecoverably blocked/stalled and replacement/fix scope is clear.

## Required checks

Inspect current state and verify:

- `@file` selected files travel from composer to backend local context and into trigger protocol.
- Backend does not read selected file contents by default.
- File browse is workspace/run scoped and rejects escapes.
- Skills registry injects metadata only on the first run of a local conversation.
- Continuation/steer/answer do not repeat skills metadata.
- Local conversation MCP tools create/list/read bounded relay store data without exposing secrets.
- `trigger.py`, `server.py` `MCP_INSTRUCTIONS`, and `docs/agent-instructions.md` agree on the protocol.

Run:

```bash
.venv/bin/python -m pytest tests/ -q
node --test frontend/tests/*.test.mjs
cd frontend && pnpm run build
git diff --check
```

## Handoff

Write `docs/workflows/2026-06-30-local-agent-shell/handoffs/V-INT.md` with:

- integrated commit/diff pointer if any
- proof commands/results
- unresolved conflicts or deferred scope
- exact next action for controller
