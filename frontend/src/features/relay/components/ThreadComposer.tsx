import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useSendShortcut } from '@/features/relay/hooks'
import { isComposerBusy, isUserReplyStatus } from '@/lib/runStatus'
import { ArrowUpIcon, LoaderCircleIcon } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'

type ComposerMode = 'idle' | 'sending' | 'waiting'

type Props = {
  conversationKey?: string
  disabled?: boolean
  mode?: ComposerMode
  onSend: (text: string) => void | Promise<void>
}

export function ThreadComposer({
  conversationKey,
  disabled = false,
  mode = 'idle',
  onSend,
}: Props) {
  const [text, setText] = useState('')
  const shortcut = useSendShortcut()
  const isBusy = mode === 'sending' || mode === 'waiting'

  const placeholder =
    mode === 'waiting'
      ? 'Waiting for agent response…'
      : mode === 'sending'
        ? 'Sending…'
        : 'Send a task to the Workspace Agent…'

  const submit = async () => {
    const trimmed = text.trim()
    if (!trimmed || isBusy || disabled) return
    setText('')
    await onSend(trimmed)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (shortcut.matches(event)) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <footer className="shrink-0 p-3">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-lg border border-input bg-background px-2 py-1.5 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || isBusy}
            className="border-0 bg-transparent px-1.5 py-1.5 shadow-none ring-0 focus-visible:ring-0 disabled:opacity-60 dark:bg-transparent"
          />
          <Button
            type="button"
            size="icon-sm"
            variant={isBusy ? 'secondary' : 'default'}
            disabled={disabled || isBusy || !text.trim()}
            onClick={() => void submit()}
            aria-label={isBusy ? 'Agent working' : 'Send'}
          >
            {isBusy ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              <ArrowUpIcon className="size-4" />
            )}
          </Button>
        </div>
        <div className="mt-1.5 px-1 text-xs text-muted-foreground">
          {isBusy ? (
            <span>{mode === 'sending' ? 'Triggering agent…' : 'Agent is working on this turn'}</span>
          ) : (
            <>
              <kbd className="rounded border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
                {shortcut.label}
              </kbd>
              <span className="ml-1.5">to send</span>
              {conversationKey ? (
                <span className="ml-2 text-muted-foreground/80">Thread linked</span>
              ) : (
                <span className="ml-2 text-muted-foreground/80">No thread selected</span>
              )}
            </>
          )}
        </div>
      </div>
    </footer>
  )
}

export type { ComposerMode }

export function resolveComposerMode(
  latestRunStatus: string | undefined,
  sending: boolean,
): ComposerMode {
  if (sending) return 'sending'
  if (isComposerBusy(latestRunStatus) && !isUserReplyStatus(latestRunStatus)) return 'waiting'
  return 'idle'
}
