import { Bug, Settings } from 'lucide-react'
import type { Conversation, RunDetail } from '@/api/types'
import { StatusBadge } from '@/components/StatusBadge'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SidebarTrigger } from '@/components/ui/sidebar'

type Props = {
  selectedConversation: Conversation | null
  selectedDetail: RunDetail | null
  loading: boolean
  recentUrl: string | null
  runCount: number
  onOpenDebug: () => void
  onOpenSettings: () => void
}

export function ThreadHeader({
  selectedConversation,
  selectedDetail,
  loading,
  recentUrl,
  runCount,
  onOpenDebug,
  onOpenSettings,
}: Props) {
  return (
    <header className="flex shrink-0 items-center gap-2 border-b px-4 py-2">
      <SidebarTrigger />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold">
          {selectedConversation?.name ?? (loading ? 'Loading...' : 'No conversation selected')}
        </h1>
        <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
          <span>
            Continuation key:{' '}
            <span className="font-mono text-foreground">
              {selectedConversation?.conversation_key ?? '-'}
            </span>
          </span>
          {recentUrl && (
            <span>
              Conversation URL:{' '}
              <a
                href={recentUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-primary hover:underline"
              >
                {recentUrl}
              </a>
            </span>
          )}
        </div>
      </div>
      {selectedDetail ? <StatusBadge status={selectedDetail.run.status} /> : null}
      <Badge variant="outline">
        {runCount} {runCount === 1 ? 'run' : 'runs'}
      </Badge>
      <Button
        variant="ghost"
        size="icon-sm"
        title="Trigger trace"
        disabled={!selectedDetail}
        onClick={onOpenDebug}
      >
        <Bug />
        <span className="sr-only">Open trigger trace</span>
      </Button>
      <Button variant="ghost" size="icon-sm" title="Settings" onClick={onOpenSettings}>
        <Settings />
        <span className="sr-only">Open settings</span>
      </Button>
      <ThemeToggle />
    </header>
  )
}
