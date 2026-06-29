import { ClipboardCopy, ExternalLink, MoreHorizontal } from 'lucide-react'
import { useCallback } from 'react'
import { toast } from 'sonner'
import type { Conversation, InteractionMode, PullSyncState } from '@/api/types'
import { Button, buttonVariants } from '@/components/ui/button'
import { PullSyncIndicator } from '@/features/relay/components/PullSyncIndicator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLinkItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { sidebarHeaderIconClass } from '@/components/ThemeMenu'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

type Props = {
  selectedConversation: Conversation | null
  selectedAgentName?: string
  loading: boolean
  recentUrl: string | null
  runCount: number
  interactionMode?: InteractionMode
  onInteractionModeChange?: (mode: InteractionMode) => void
  interactionModePending?: boolean
  pullSyncVisible?: boolean
  pullSyncState?: PullSyncState
  pullSyncIntervalSec?: number
  onPullSyncResume?: () => void
  pullSyncResumePending?: boolean
}

export function ThreadHeader({
  selectedConversation,
  selectedAgentName,
  loading,
  recentUrl,
  runCount,
  interactionMode = 'relay',
  onInteractionModeChange,
  interactionModePending = false,
  pullSyncVisible = false,
  pullSyncState = 'idle',
  pullSyncIntervalSec = 5,
  onPullSyncResume,
  pullSyncResumePending = false,
}: Props) {
  const title = selectedConversation?.name ?? (loading ? 'Loading...' : 'No conversation selected')
  const conversationKey = selectedConversation?.conversation_key

  const subtitleParts = [
    selectedAgentName,
    runCount > 0 ? `${runCount} ${runCount === 1 ? 'turn' : 'turns'}` : null,
  ].filter(Boolean)

  const handleCopyKey = useCallback(async () => {
    if (!conversationKey) return
    try {
      await navigator.clipboard.writeText(conversationKey)
      toast.success('Continuation key copied')
    } catch {
      toast.error('Clipboard unavailable')
    }
  }, [conversationKey])

  const hasMenuActions = Boolean(conversationKey || recentUrl)
  const showModeToggle = Boolean(selectedConversation && onInteractionModeChange)

  return (
    <header className="flex min-h-12 shrink-0 items-center gap-2 border-b border-border px-3 py-2">
      <SidebarTrigger className={sidebarHeaderIconClass} />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold" title={title}>
          {title}
        </h1>
        {subtitleParts.length > 0 ? (
          <p className="truncate text-[11px] text-muted-foreground">{subtitleParts.join(' · ')}</p>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {showModeToggle ? (
          <div
            className="flex items-center rounded-md border border-border p-0.5"
            role="group"
            aria-label="Interaction mode"
          >
            {(['relay', 'pull'] as const).map((mode) => (
              <Button
                key={mode}
                type="button"
                size="sm"
                variant={interactionMode === mode ? 'secondary' : 'ghost'}
                className="h-7 px-2.5 text-xs capitalize"
                disabled={interactionModePending}
                onClick={() => {
                  if (mode !== interactionMode) onInteractionModeChange?.(mode)
                }}
              >
                {mode}
              </Button>
            ))}
          </div>
        ) : null}
        {pullSyncVisible ? (
          <PullSyncIndicator
            state={pullSyncState}
            intervalActiveSec={pullSyncIntervalSec}
            onResume={onPullSyncResume}
            resumePending={pullSyncResumePending}
          />
        ) : null}
        {hasMenuActions ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              className={cn(buttonVariants({ variant: 'ghost', size: 'icon-sm' }))}
              title="Conversation actions"
            >
              <MoreHorizontal />
              <span className="sr-only">Conversation actions</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              {conversationKey ? (
                <DropdownMenuItem onClick={() => void handleCopyKey()}>
                  <ClipboardCopy />
                  Copy continuation key
                </DropdownMenuItem>
              ) : null}
              {recentUrl ? (
                <DropdownMenuLinkItem href={recentUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink />
                  Open in ChatGPT
                </DropdownMenuLinkItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </header>
  )
}
