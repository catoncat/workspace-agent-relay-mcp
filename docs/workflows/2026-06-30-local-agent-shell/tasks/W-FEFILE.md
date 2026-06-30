# W-FEFILE — Frontend `@file` composer experience

## Objective

Implement the frontend half of `@file`:

- workspace/run scoped file picker UI in the composer
- visible selected file references
- structured `selected_files` sent with create-run and steer requests
- existing queue/steer/Enter behavior preserved

Use the design spec at `docs/superpowers/specs/2026-06-30-local-agent-shell-protocol.md`.

## Mode

implementation-slice

## Allowed writes

- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/relay/components/ThreadComposer.tsx`
- `frontend/src/features/relay/composerController.ts`
- `frontend/src/features/relay/queueModel.ts` if selected-file context must follow queued messages
- `frontend/src/features/relay/hooks.ts`
- `frontend/src/pages/RelayPage.tsx`
- new frontend components under `frontend/src/features/relay/components/`
- `frontend/tests/`
- `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-FEFILE.md`

Do not edit backend `src/` files in this task.

## Expected backend contract

Assume W-CORE will provide:

```ts
type SelectedFileContext = {
  path: string
  workspace_relative_path?: string
}

type LocalContext = {
  selected_files?: SelectedFileContext[]
}
```

Create run and steer request bodies may include:

```json
{
  "input_markdown": "...",
  "local_context": {
    "selected_files": [
      {"path": "/absolute/workspace/src/foo.py", "workspace_relative_path": "src/foo.py"}
    ]
  }
}
```

File browse response shape:

```ts
type WorkspaceFileBrowseResult = {
  root: string
  path: string
  parent: string | null
  entries: Array<{
    name: string
    path: string
    workspace_relative_path: string
    kind: 'file' | 'directory'
  }>
  truncated: boolean
}
```

The exact endpoint may be adjusted during integration, but prefer:

- `GET /api/workspaces/:workspaceId/browse-files?path=...`
- `GET /api/runs/:runId/browse-files?path=...` if active steer uses an old working-directory snapshot

## Required behavior

1. Typing or clicking `@` exposes a file picker when a file-browse target exists.
2. The picker lists directories and files, supports navigating into directories, parent navigation, and selecting files.
3. Selecting a file adds a visible file reference/chip and keeps the text editable.
4. Submitting sends the text plus structured `selected_files`.
5. Queued messages preserve their own selected-file context; steering a queued message sends that message's context.
6. No unsupported context types are added.
7. Existing composer behavior remains:
   - Enter sends
   - Shift+Enter newline
   - Cmd/Ctrl+Enter steer
   - IME composition safe
   - queue flush still merges queued text correctly

## Required tests

Add or update focused frontend tests for pure controller/model behavior:

- send plan preserves selected file context
- queued messages retain selected file context
- queue flush merges text and selected file context deterministically
- steer queued message uses that message's selected files

Run:

```bash
node --test frontend/tests/*.test.mjs
cd frontend && pnpm run build
```

If a UI detail cannot be covered by existing node tests, document what build/typecheck covers and what needs later browser verification.

## Handoff

Write `docs/workflows/2026-06-30-local-agent-shell/handoffs/W-FEFILE.md` with:

- changed files
- implementation summary
- exact proof commands/results
- expected backend endpoint/type assumptions
- known integration risks with W-CORE
- noise/efficiency notes
