import type { CSSProperties } from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type StatusMeta = {
  label: string
  token: string
}

const STATUS_META: Record<string, StatusMeta> = {
  accepted: { label: 'Accepted', token: '--status-pending' },
  waiting: { label: 'Waiting', token: '--status-pending' },
  pending: { label: 'Pending', token: '--status-pending' },
  running: { label: 'Running', token: '--status-running' },
  progress: { label: 'In progress', token: '--status-running' },
  draft: { label: 'Draft', token: '--status-info' },
  done: { label: 'Done', token: '--status-done' },
  result: { label: 'Result', token: '--status-done' },
  failed: { label: 'Failed', token: '--status-failed' },
  trigger_failed: { label: 'Trigger failed', token: '--status-failed' },
  blocked: { label: 'Blocked', token: '--status-failed' },
  needs_user: { label: 'Needs user', token: '--status-info' },
  question: { label: 'Question', token: '--status-info' },
  ask_user: { label: 'Needs user', token: '--status-info' },
}

const PULSE_STATUSES = new Set(['accepted', 'waiting', 'pending', 'running', 'progress'])

export function StatusBadge({ status }: { status?: string }) {
  const key = status || 'unknown'
  const meta = STATUS_META[key] ?? { label: labelizeStatus(key), token: '--status-info' }
  const pulse = PULSE_STATUSES.has(key)
  const style = {
    color: `var(${meta.token})`,
    borderColor: `color-mix(in oklch, var(${meta.token}), transparent 70%)`,
    backgroundColor: `color-mix(in oklch, var(${meta.token}), transparent 90%)`,
  } satisfies CSSProperties

  return (
    <Badge variant="outline" style={style} className="gap-1 border-current/30">
      <span
        aria-hidden="true"
        className={cn('size-1.5 rounded-full bg-current opacity-80', pulse && 'motion-safe:animate-pulse')}
      />
      {meta.label}
    </Badge>
  )
}

function labelizeStatus(status: string): string {
  return status
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}
