import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { SendIntent } from '@/features/relay/sendIntent'
import { isComposerBusy, isUserReplyStatus } from '@/lib/runStatus'
import { cn } from '@/lib/utils'
import {
  ArrowUpIcon,
  CornerDownRightIcon,
  Edit3Icon,
  ListPlusIcon,
  LoaderCircleIcon,
  MoreHorizontalIcon,
  SquareIcon,
  Trash2Icon,
} from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

type ComposerMode = 'idle' | 'sending' | 'waiting' | 'replying'

type Props = {
  conversationKey?: string
  disabled?: boolean
  dismissing?: boolean
  mode?: ComposerMode
  canSteer?: boolean
  onDismiss?: () => void | Promise<void>
  onSend: (text: string, intent: SendIntent) => void | Promise<void>
}

export function ThreadComposer({
  disabled = false,
  dismissing = false,
  mode = 'idle',
  canSteer = false,
  onDismiss,
  onSend,
}: Props) {
  const [text, setText] = useState('')
  const [intent, setIntent] = useState<SendIntent>('queue')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
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

  const isReplying = mode === 'replying'
  const showModeBar = canSteer && !disabled
  const effectiveIntent = showModeBar ? intent : 'queue'
  const placeholder =
    mode === 'sending'
      ? 'Sending…'
      : showModeBar && effectiveIntent === 'steer'
        ? '要求后续变更'
        : showModeBar
          ? '提交新请求，排队执行…'
          : isReplying
            ? 'Answer the agent…'
            : isAgentWorking
              ? 'Send a queued request…'
              : 'Send a task to the Workspace Agent…'

  useEffect(() => {
    if (!showModeBar && intent !== 'queue') setIntent('queue')
  }, [intent, showModeBar])

  const submit = async (intentOverride?: SendIntent) => {
    const trimmed = text.trim()
    if (!trimmed || disabled || isSending) return
    setText('')
    await onSend(trimmed, intentOverride ?? effectiveIntent)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter') return
    if (event.nativeEvent.isComposing) return
    if (event.shiftKey) return
    event.preventDefault()
    void submit(event.metaKey || event.ctrlKey ? 'steer' : undefined)
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
          : effectiveIntent === 'steer'
            ? 'Send as guidance'
            : isReplying
              ? 'Queue as new request'
              : isAgentWorking
                ? 'Queue new request'
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
        {showModeBar ? (
          <div className="mx-10 -mb-px flex h-12 items-center justify-between rounded-t-3xl border border-input bg-background px-4 text-sm text-muted-foreground shadow-xs">
            <button
              type="button"
              className="flex min-w-0 items-center gap-2 rounded-full px-1.5 py-1 text-left transition-colors hover:text-foreground"
              onClick={() => setIntent((value) => (value === 'steer' ? 'queue' : 'steer'))}
              title={effectiveIntent === 'steer' ? '当前发送方式：引导当前任务' : '当前发送方式：排队为新请求'}
            >
              {effectiveIntent === 'steer' ? (
                <CornerDownRightIcon className="size-4 shrink-0" />
              ) : (
                <ListPlusIcon className="size-4 shrink-0" />
              )}
              <span className="truncate text-base font-medium text-foreground">
                {effectiveIntent === 'steer' ? '引导' : '排队'}
              </span>
            </button>

            <div className="flex shrink-0 items-center gap-1">
              <Button
                type="button"
                variant={effectiveIntent === 'steer' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-8 rounded-full px-3 text-sm"
                onClick={() => setIntent((value) => (value === 'steer' ? 'queue' : 'steer'))}
                title="切换引导模式；Cmd+Enter 可直接按引导发送"
              >
                <CornerDownRightIcon className="size-4" />
                引导
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="rounded-full text-muted-foreground"
                disabled={!hasText}
                onClick={() => {
                  setText('')
                  textareaRef.current?.focus()
                }}
                title="清空消息"
              >
                <Trash2Icon className="size-4" />
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger
                  className="inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  title="发送选项"
                >
                  <MoreHorizontalIcon className="size-4" />
                  <span className="sr-only">发送选项</span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                  <DropdownMenuItem onClick={() => textareaRef.current?.focus()}>
                    <Edit3Icon />
                    编辑消息
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => setIntent(effectiveIntent === 'steer' ? 'queue' : 'steer')}
                  >
                    {effectiveIntent === 'steer' ? (
                      <ListPlusIcon />
                    ) : (
                      <CornerDownRightIcon />
                    )}
                    {effectiveIntent === 'steer' ? '启用队列模式' : '启用引导模式'}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        ) : null}
        <div
          className={cn(
            'flex items-end gap-2 border border-input bg-background px-3 py-2 shadow-xs transition-[border-radius,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50',
            showModeBar ? 'rounded-b-3xl rounded-t-none' : isMultiline ? 'rounded-2xl' : 'rounded-full',
          )}
        >
          <Textarea
            ref={textareaRef}
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
  if (isUserReplyStatus(latestRunStatus)) return 'replying'
  return 'idle'
}
