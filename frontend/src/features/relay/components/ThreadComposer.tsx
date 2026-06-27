import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ArrowUpIcon, LoaderCircleIcon } from 'lucide-react'
import { useSendShortcut } from '@/features/relay/hooks'
import { useState, type KeyboardEvent } from 'react'

type Props = {
  conversationKey?: string
  disabled?: boolean
  sending?: boolean
  onSend: (text: string) => void | Promise<void>
}

export function ThreadComposer({ conversationKey, disabled = false, sending = false, onSend }: Props) {
  const [text, setText] = useState('')
  const threadState = conversationKey ? 'Thread linked' : 'No thread selected'
  const shortcut = useSendShortcut()

  const submit = async () => {
    const trimmed = text.trim()
    if (!trimmed || sending || disabled) return
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
            placeholder="Send a task to the Workspace Agent..."
            className="border-0 bg-transparent px-1.5 py-1.5 shadow-none ring-0 focus-visible:ring-0 dark:bg-transparent"
          />
          <Button
            type="button"
            size="icon-sm"
            disabled={sending || disabled || !text.trim()}
            onClick={() => void submit()}
            aria-label="Send"
          >
            {sending ? (
              <LoaderCircleIcon className="size-4 animate-spin" />
            ) : (
              <ArrowUpIcon className="size-4" />
            )}
          </Button>
        </div>
        <div className="mt-1.5 px-1 text-xs text-muted-foreground">
          <kbd className="rounded border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
            {shortcut.label}
          </kbd>
          <span className="ml-1.5">to send</span>
          <span className="ml-2 text-muted-foreground/80">{threadState}</span>
        </div>
      </div>
    </footer>
  )
}
