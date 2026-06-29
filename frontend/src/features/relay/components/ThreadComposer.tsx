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
import type { QueuedComposerMessage } from '@/features/relay/queueModel'
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
  queuedMessages?: QueuedComposerMessage[]
  queueFlushPending?: boolean
  onDismiss?: () => void | Promise<void>
  onSend: (text: string, intent: SendIntent) => void | Promise<void>
  onQueuedMessageDelete?: (id: string) => void
  onQueuedMessageEdit?: (id: string, text: string) => void
  onQueuedMessageSteer?: (id: string) => void | Promise<void>
  onCloseQueue?: () => void
}

export function ThreadComposer({
  disabled = false,
  dismissing = false,
  mode = 'idle',
  canSteer = false,
  queuedMessages = [],
  queueFlushPending = false,
  onDismiss,
  onSend,
  onQueuedMessageDelete,
  onQueuedMessageEdit,
  onQueuedMessageSteer,
  onCloseQueue,
}: Props) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const isSending = mode === 'sending'
  const isAgentWorking = mode === 'waiting'
  const hasText = Boolean(text.trim())
  const isMultiline = text.includes('\n')
  const showWorkingButton = isSending || dismissing || (isAgentWorking && !hasText)

  const isReplying = mode === 'replying'
  const hasQueuedMessages = queuedMessages.length > 0
  const placeholder =
    mode === 'sending'
      ? 'Sending…'
      : isReplying
        ? '回答 Agent…'
        : isAgentWorking
          ? '要求后续变更'
          : '发送任务给 Workspace Agent…'

  const submit = async (intentOverride?: SendIntent) => {
    const trimmed = text.trim()
    if (!trimmed || disabled || isSending) return
    setText('')
    const intent = intentOverride ?? (isReplying && canSteer ? 'steer' : 'queue')
    await onSend(trimmed, intent)
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
          : isReplying
            ? 'Answer agent'
            : isAgentWorking
              ? 'Queue message'
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
        {hasQueuedMessages ? (
          <div
            className={cn(
              'relative z-0 mx-2 mb-[-10px] rounded-t-2xl border border-input bg-background px-3 pt-2 pb-5 text-sm shadow-xs sm:mx-10 sm:rounded-t-3xl sm:px-4',
              queueFlushPending && 'ring-1 ring-primary/15',
            )}
          >
            <div className="flex flex-col gap-1">
              {queuedMessages.map((message) => (
                <QueuedMessageRow
                  key={message.id}
                  message={message}
                  canSteer={canSteer && !disabled && !isSending}
                  queueFlushPending={queueFlushPending}
                  onDelete={() => onQueuedMessageDelete?.(message.id)}
                  onEdit={(nextText) => onQueuedMessageEdit?.(message.id, nextText)}
                  onSteer={() => void onQueuedMessageSteer?.(message.id)}
                  onCloseQueue={onCloseQueue}
                />
              ))}
            </div>
          </div>
        ) : null}
        <div
          className={cn(
            'relative z-10 flex items-end gap-2 border border-input bg-background px-3 py-2 shadow-xs transition-[border-radius,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50',
            isMultiline ? 'rounded-2xl' : 'rounded-full',
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
      </div>
    </footer>
  )
}

function QueuedMessageRow({
  message,
  canSteer,
  queueFlushPending,
  onDelete,
  onEdit,
  onSteer,
  onCloseQueue,
}: {
  message: QueuedComposerMessage
  canSteer: boolean
  queueFlushPending: boolean
  onDelete?: () => void
  onEdit?: (text: string) => void
  onSteer?: () => void
  onCloseQueue?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.text)

  useEffect(() => {
    if (!editing) setDraft(message.text)
  }, [editing, message.text])

  const saveEdit = () => {
    const trimmed = draft.trim()
    if (!trimmed) return
    onEdit?.(trimmed)
    setEditing(false)
  }

  const cancelEdit = () => {
    setDraft(message.text)
    setEditing(false)
  }

  const handleEditKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancelEdit()
      return
    }
    if (event.key !== 'Enter') return
    if (event.nativeEvent.isComposing) return
    if (event.shiftKey) return
    event.preventDefault()
    saveEdit()
  }

  if (editing) {
    return (
      <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-x-2 gap-y-2 py-1 sm:flex sm:items-start sm:gap-2">
        <CornerDownRightIcon className="mt-2 size-4 shrink-0 text-muted-foreground" />
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleEditKeyDown}
          rows={Math.min(4, Math.max(1, draft.split('\n').length))}
          className="min-h-24 w-full min-w-0 resize-none rounded-xl border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 sm:min-h-8 sm:flex-1"
          autoFocus
        />
        <div className="col-start-2 flex min-h-10 shrink-0 items-center justify-end gap-1 sm:col-start-auto sm:min-h-0 sm:justify-start sm:pt-0.5">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-10 rounded-full px-4 sm:h-7 sm:px-2.5"
            disabled={!draft.trim()}
            onClick={saveEdit}
          >
            保存
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-10 rounded-full px-4 sm:h-7 sm:px-2.5"
            onClick={cancelEdit}
          >
            取消
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-9 items-center gap-2">
      {queueFlushPending ? (
        <LoaderCircleIcon className="size-4 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <CornerDownRightIcon className="size-4 shrink-0 text-muted-foreground" />
      )}
      <div className="min-w-0 flex-1 truncate text-base text-foreground">{message.text}</div>
      <div className="flex shrink-0 items-center gap-1 text-muted-foreground">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 rounded-full px-2.5 text-sm text-muted-foreground"
          disabled={!canSteer}
          onClick={onSteer}
          title="立即作为引导发送给当前任务"
        >
          <CornerDownRightIcon className="size-4" />
          引导
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="rounded-full text-muted-foreground"
          onClick={onDelete}
          title="取消这条排队消息"
        >
          <Trash2Icon className="size-4" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger
            className="inline-flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            title="排队消息选项"
          >
            <MoreHorizontalIcon className="size-4" />
            <span className="sr-only">排队消息选项</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem onClick={() => setEditing(true)}>
              <Edit3Icon />
              编辑消息
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onCloseQueue} disabled={queueFlushPending}>
              <ListPlusIcon />
              {queueFlushPending ? '已关闭排队' : '关闭排队'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
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
