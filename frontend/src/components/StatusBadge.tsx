import { Badge } from '@/components/ui/badge'
import type { VariantProps } from 'class-variance-authority'
import type { badgeVariants } from '@/components/ui/badge'

type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  accepted: 'secondary',
  waiting: 'secondary',
  pending: 'secondary',
  running: 'default',
  draft: 'outline',
  done: 'outline',
  failed: 'destructive',
  blocked: 'destructive',
  needs_user: 'secondary',
  progress: 'default',
  question: 'secondary',
  ask_user: 'secondary',
  result: 'outline',
}

const PULSE_STATUSES = new Set(['accepted', 'waiting', 'pending', 'running', 'progress'])

export function StatusBadge({ status }: { status?: string }) {
  const key = status || 'unknown'
  const variant = STATUS_VARIANTS[key] ?? 'outline'
  const pulse = PULSE_STATUSES.has(key)
  return (
    <Badge variant={variant} className="gap-1">
      <span className={`size-1.5 rounded-full bg-current opacity-80 ${pulse ? 'animate-pulse' : ''}`} />
      {key}
    </Badge>
  )
}
