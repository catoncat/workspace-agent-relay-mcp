import { ClipboardCopy, ExternalLink, MoreHorizontal } from 'lucide-react'
import { useCallback } from 'react'
import { toast } from 'sonner'
import type { Conversation } from '@/api/types'
import { buttonVariants } from '@/components/ui/button'
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
  loading: boolean
  recentUrl: string | null
  runCount: number
}

export function ThreadHeader({
  selectedConversation,
  loading,
  recentUrl,
  runCount,
}: Props) {
  const title = selectedConversation?.name ?? (loading ? 'Loading...' : 'No conversation selected')
  const conversationKey = selectedConversation?.conversation_key

  const subtitleParts = [
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
