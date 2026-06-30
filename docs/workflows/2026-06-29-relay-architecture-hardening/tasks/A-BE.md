# A-BE Backend / Protocol Audit

## Objective

Independently audit backend-side closure for report items R1, R2 backend half, R4, R5, and R6 against `origin/main`.

## Mode

read-only audit-track. Do not edit product code. You may write the assigned handoff only.

## Read

- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/AGENTS.md`
- `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/closure-matrix.md`
- source report: `/var/folders/vn/4x0ljfzs2bjff2j7w_m60__h0000gn/T/architecture-review-20260629-202248.html`
- current code at `origin/main`

## Audit Questions

1. R1: Does backend store status mutation consistently go through `run_lifecycle.py` or equivalent? Are late progress after `ask_user`, late callbacks after `trigger_failed`, and terminal/user-reply boundaries actually covered?
2. R2 backend: Does create run reject blank input consistently with steer? Are API route semantics consistent with background trigger dispatch?
3. R4: Is trigger dispatch adapter lifecycle owned by app lifespan? Is task cleanup, exception redaction, shutdown/drain behavior implemented and tested?
4. R5: Does `/internal/tool-trace` validate optional payload types and preserve normalized payload invariants?
5. R6: Is workspace directory OS/path adapter separated from HTTP route with mockable tests?

## Required Output

Write `/Users/envvar/work/repos/poke/workspace-agent-relay-mcp/docs/workflows/2026-06-29-relay-architecture-hardening/handoffs/A-BE.md` with:

- verdict per item: `closed`, `needs-fix`, or `uncertain`.
- exact file/line evidence.
- tests/proof already present and any test gaps.
- if `needs-fix`, minimal implementation recommendation and likely touched files.
- noise/events and whether you had to deviate from read-only.

Do not push, commit, deploy, or modify product files.
