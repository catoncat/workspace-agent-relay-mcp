import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { isComposerBusy, isUserReplyStatus } from '@/lib/runStatus'
import { cn } from '@/lib/utils'
import { ArrowUpIcon, LoaderCircleIcon, SquareIcon } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'

type ComposerMode = 'idle' | 'sending' | 'waiting'

type Props = {
  conversationKey?: string
  disabled?: boolean
  dismissing?: boolean
  mode?: ComposerMode
  onDismiss?: () => void | Promise<void>
  onSend: (text: string) => void | Promise<void>
}

export function ThreadComposer({
  disabled = false,
  dismissing = false,
  mode = 'idle',
  onDismiss,
  onSend,
}: Props) {
  const [text, setText] = useState('')
  const isSending = mode === 'sending'
  const isAgentWorking = mode === 'waiting'
  const hasText = Boolean(text.trim())
  const isMultiline = text.includes('\n')
  const showWorkingButton = isSending || dismissing || (isAgentWorking && !hasText)
  const statusText = isSending
    ? 'Triggering agent…'
    : dismissing
      ? 'Marking turn as finished…'
      : null

  const placeholder =
    mode === 'sending'
      ? 'Sending…'
      : isAgentWorking
        ? 'Add instruction to current work…'
      : isMultiline
        ? 'Send follow-up…'
        : 'Send a task to the Workspace Agent…'

  const submit = async () => {
    const trimmed = text.trim()
    if (!trimmed || disabled || isSending) return
    setText('')
    await onSend(trimmed)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter') return
    if (event.nativeEvent.isComposing) return
    if (event.shiftKey) return
    event.preventDefault()
    void submit()
  }

  const handleButtonClick = () => {
    if (isAgentWorking && !hasText && !isSending && onDismiss) {
      void onDismiss()
      return
    }
    void submit()
  }

  const actionButton = (
    <Button
      type="button"
      size="icon"
      variant={showWorkingButton ? 'secondary' : 'default'}
      disabled={disabled || isSending || dismissing || (!showWorkingButton && !hasText)}
      onClick={handleButtonClick}
      aria-label={
        showWorkingButton
          ? isAgentWorking && !hasText && !isSending
            ? 'Mark turn finished'
            : 'Agent working'
          : isAgentWorking
            ? 'Send follow-up instruction'
            : 'Send'
      }
      className={cn(
        'mb-0.5 size-8 shrink-0 rounded-full',
        showWorkingButton && 'bg-muted text-muted-foreground',
        !showWorkingButton && hasText && 'bg-primary text-primary-foreground hover:bg-primary/90',
      )}
    >
      {showWorkingButton ? (
        isAgentWorking && !hasText && !isSending && !dismissing ? (
          <SquareIcon className="size-3 fill-current" strokeWidth={0} />
        ) : (
          <LoaderCircleIcon className="size-4 animate-spin" />
        )
      ) : (
        <ArrowUpIcon className="size-4" strokeWidth={2.5} />
      )}
    </Button>
  )

  return (
    <footer className="shrink-0 p-3">
      <div className="mx-auto max-w-3xl">
        <div
          className={cn(
            'flex items-end gap-2 border border-input bg-background px-3 py-2 shadow-xs transition-[border-radius,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50',
            isMultiline ? 'rounded-2xl' : 'rounded-full',
          )}
        >
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={isMultiline ? 2 : 1}
            className={cn(
              'border-0 bg-transparent px-0 py-1.5 shadow-none ring-0 focus-visible:ring-0 disabled:opacity-60 dark:bg-transparent',
              isMultiline
                ? 'field-sizing-content min-h-16 max-h-48 resize-none'
                : 'min-h-0 h-9 max-h-9 resize-none overflow-hidden leading-normal',
            )}
          />
          {isAgentWorking && !hasText && !isSending ? (
            <TooltipProvider delay={200}>
              <Tooltip>
                <TooltipTrigger render={actionButton} />
                <TooltipContent side="top" className="max-w-xs text-left font-sans">
                  Trigger runs cannot be stopped remotely. Click to mark this turn finished when you
                  know the agent is done.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            actionButton
          )}
        </div>
        {statusText ? <div className="mt-1.5 px-1 text-xs text-muted-foreground">{statusText}</div> : null}
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
