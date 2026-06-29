import type { RunStatus } from '@/api/types'

export const RUN_ACTIVE_STATUSES: ReadonlySet<RunStatus> = new Set([
  'draft',
  'sent',
  'pending',
  'running',
  'accepted',
  'waiting',
  'needs_user',
  'trigger_failed',
])

export const RUN_TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set(['done', 'blocked', 'failed', 'superseded'])

/** Run is in-flight; composer send button shows a spinner until the user types to steer. */
export const RUN_COMPOSER_BUSY_STATUSES: ReadonlySet<RunStatus> = new Set([
  'draft',
  'sent',
  'pending',
  'running',
  'accepted',
  'waiting',
  'progress',
])

export const RUN_USER_REPLY_STATUSES: ReadonlySet<RunStatus> = new Set(['needs_user', 'question', 'ask_user'])

export function isComposerBusy(status: RunStatus | undefined): boolean {
  if (!status) return false
  return RUN_COMPOSER_BUSY_STATUSES.has(status)
}

/** Latest run is in-flight (matches ThreadComposer "waiting" / agent working). */
export function isConversationWorking(status: RunStatus | undefined): boolean {
  if (!status) return false
  return isComposerBusy(status) && !isUserReplyStatus(status)
}

export function latestRunStatusFromRuns(
  runs: ReadonlyArray<{ id: number; status: RunStatus }> | undefined,
): RunStatus | undefined {
  if (!runs?.length) return undefined
  let latest = runs[0]!
  for (const run of runs) {
    if (run.id > latest.id) latest = run
  }
  return latest.status
}

export function isUserReplyStatus(status: RunStatus | undefined): boolean {
  if (!status) return false
  return RUN_USER_REPLY_STATUSES.has(status)
}

/** Only surface a header badge for exceptional states worth calling out. */
export const RUN_HEADER_BADGE_STATUSES: ReadonlySet<RunStatus> = new Set([
  'failed',
  'trigger_failed',
  'blocked',
  'needs_user',
  'question',
  'ask_user',
])

export function shouldShowHeaderStatusBadge(status: RunStatus | undefined): boolean {
  if (!status) return false
  return RUN_HEADER_BADGE_STATUSES.has(status)
}
