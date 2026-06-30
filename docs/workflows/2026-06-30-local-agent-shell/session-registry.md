# Session Registry

| Task | Role | Run | Title | Thread/Agent | Worktree | Branch | Commit | Status | Proof | Handoff | Next |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A-FILE | explorer | 20260630 | Local Agent Shell: Explorer - @file | 019f14a7-7949-7981-be65-af0a152ce06e | controller workspace, read-only | n/a | none | closed | composer pure text; existing browse API directories-only; need workspace-scoped file metadata API | none | synthesize W-FILE |
| A-CONV | explorer | 20260630 | Local Agent Shell: Explorer - Conversations MCP | 019f14a7-94d4-7760-ace9-f39c4974c73a | controller workspace, read-only | n/a | none | closed | store has conversations/runs/events; MCP lacks local conversation create/list/read tools | none | synthesize W-CONV |
| A-SKILL | explorer | 20260630 | Local Agent Shell: Explorer - Skills Prelude | 019f14a7-b125-70c0-92c1-04b1d5d60af1 | controller workspace, read-only | n/a | none | closed | initial branch is right injection point; registry should scan metadata only and not repeat on continuation/steer | none | synthesize W-SKILL |
| A-PROTO | explorer | 20260630 | Local Agent Shell: Explorer - Prompt Protocol | 019f14a7-d7dc-7592-b4d4-a3c1f5bd35d5 | controller workspace, read-only | n/a | none | closed | protocol should be envelope + local context entities + concise tool contract | none | synthesize W-PROTO |

## Planned Durable Sessions

| Task | Role | Status | Scope | Launch condition |
| --- | --- | --- | --- | --- |
| W-CORE | worker | closed | backend protocol, selected-file validation/browse, skills registry, local conversation MCP tools | thread `019f14bd-12a1-79f0-8e75-cbd6bc839068`; worktree `/Users/envvar/.codex/worktrees/bea2/workspace-agent-relay-mcp`; handoff copied to canonical control plane; controller verification passed; thread unpinned/archived |
| W-FEFILE | worker | closed | frontend `@file` composer, selected-file context through queue/steer/send | thread `019f14bd-3284-7af1-8bc8-74f651f3c3f2`; worktree `/Users/envvar/.codex/worktrees/83b3/workspace-agent-relay-mcp`; handoff copied to canonical control plane; controller verification passed; thread unpinned/archived |
| V-INT | verifier | complete | integrated pytest/frontend build/protocol sync/browser smoke proof | handoff: `docs/workflows/2026-06-30-local-agent-shell/handoffs/V-INT.md` |
| CTRL-FINAL | controller | lifecycle-gated | final requirement audit and publication boundary packet | handoff: `docs/workflows/2026-06-30-local-agent-shell/handoffs/controller-final.md` |

## Noise Events

- 2026-06-30: Controller checkout already contained staged and unstaged product changes. Controller will not revert, stage, or commit them; implementation sessions must use isolated worktrees and record their baseline.
- 2026-06-30: Controller integration verification passed; lifecycle actions remain unauthorized.
- 2026-06-30: Controller directly integrated worker output into the dirty checkout after handoffs. This is recorded as an integration exception; final verification passed afterward.
