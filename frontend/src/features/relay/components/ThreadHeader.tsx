import { Bug, ClipboardCopy, Check, ExternalLink, Settings } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
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
  const title = selectedConversation?.name ?? (loading ? 'Loading...' : 'No conversation selected')
  const conversationKey = selectedConversation?.conversation_key
  const [copied, setCopied] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current !== null) {
        window.clearTimeout(copyTimeoutRef.current)
      }
    }
  }, [])

  const handleCopyKey = useCallback(async () => {
    if (!conversationKey) return
    try {
      await navigator.clipboard.writeText(conversationKey)
      setCopied(true)
      toast.success('Continuation key copied')
      if (copyTimeoutRef.current !== null) {
        window.clearTimeout(copyTimeoutRef.current)
      }
      copyTimeoutRef.current = window.setTimeout(() => {
        setCopied(false)
        copyTimeoutRef.current = null
      }, 1500)
    } catch {
      toast.error('Clipboard unavailable')
    }
  }, [conversationKey])

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3">
      <SidebarTrigger />
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold" title={title}>
        {title}
      </h1>

      <div className="flex shrink-0 items-center gap-1.5">
        {selectedDetail ? <StatusBadge status={selectedDetail.run.status} /> : null}
        <Badge variant="secondary" className="tabular-nums">
          {runCount} {runCount === 1 ? 'run' : 'runs'}
        </Badge>

        {conversationKey ? (
          <Button
            variant="ghost"
            size="icon-sm"
            title="Copy continuation key"
            onClick={handleCopyKey}
          >
            {copied ? <Check /> : <ClipboardCopy />}
            <span className="sr-only">Copy continuation key</span>
          </Button>
        ) : null}

        {recentUrl ? (
          <Button
            render={<a href={recentUrl} target="_blank" rel="noopener noreferrer" />}
            variant="ghost"
            size="icon-sm"
            title={`Open conversation: ${recentUrl}`}
          >
            <ExternalLink />
            <span className="sr-only">Open conversation</span>
          </Button>
        ) : null}

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
        <ThemeToggle size="icon-sm" />
      </div>
    </header>
  )
}
