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
import type {
  LocalContext,
  RunStatus,
  SelectedFileContext,
  WorkspaceFileBrowseResult,
} from '@/api/types'
import { isComposerBusy, isUserReplyStatus } from '@/lib/runStatus'
import { cn } from '@/lib/utils'
import {
  ArrowUpIcon,
  AtSignIcon,
  ChevronLeftIcon,
  CornerDownRightIcon,
  Edit3Icon,
  FileIcon,
  FolderIcon,
  ListPlusIcon,
  LoaderCircleIcon,
  MoreHorizontalIcon,
  SquareIcon,
  Trash2Icon,
  XIcon,
} from 'lucide-react'
import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'

type ComposerMode = 'idle' | 'sending' | 'waiting' | 'replying'

type Props = {
  conversationKey?: string
  disabled?: boolean
  dismissing?: boolean
  focusToken?: number
  mode?: ComposerMode
  canSteer?: boolean
  canBrowseFiles?: boolean
  queuedMessages?: QueuedComposerMessage[]
  queueFlushPending?: boolean
  onDismiss?: () => void | Promise<void>
  onSend: (text: string, intent: SendIntent, localContext?: LocalContext) => void | Promise<void>
  onBrowseFiles?: (path?: string | null) => Promise<WorkspaceFileBrowseResult>
  onQueuedMessageDelete?: (id: string) => void
  onQueuedMessageEdit?: (id: string, text: string) => void
  onQueuedMessageSteer?: (id: string) => void | Promise<void>
  onCloseQueue?: () => void
}

export function ThreadComposer({
  disabled = false,
  dismissing = false,
  focusToken = 0,
  mode = 'idle',
  canSteer = false,
  canBrowseFiles = false,
  queuedMessages = [],
  queueFlushPending = false,
  onDismiss,
  onSend,
  onBrowseFiles,
  onQueuedMessageDelete,
  onQueuedMessageEdit,
  onQueuedMessageSteer,
  onCloseQueue,
}: Props) {
  const [text, setText] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<SelectedFileContext[]>([])
  const [filePickerOpen, setFilePickerOpen] = useState(false)
  const [browsePath, setBrowsePath] = useState<string | null>(null)
  const [browseResult, setBrowseResult] = useState<WorkspaceFileBrowseResult | null>(null)
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const isSending = mode === 'sending'
  const isAgentWorking = mode === 'waiting'
  const hasText = Boolean(text.trim())
  const isMultiline = text.includes('\n')
  const showWorkingButton = isSending || dismissing || (isAgentWorking && !hasText)
  const canUseFilePicker = canBrowseFiles && Boolean(onBrowseFiles) && !disabled

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

  useEffect(() => {
    if (disabled) return
    textareaRef.current?.focus()
  }, [disabled, focusToken])

  useEffect(() => {
    if (!filePickerOpen || !onBrowseFiles) return
    let cancelled = false
    setBrowseLoading(true)
    setBrowseError(null)
    void onBrowseFiles(browsePath)
      .then((result) => {
        if (cancelled) return
        setBrowseResult(result)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setBrowseError(error instanceof Error ? error.message : String(error))
      })
      .finally(() => {
        if (!cancelled) setBrowseLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [browsePath, filePickerOpen, onBrowseFiles])

  const openFilePicker = () => {
    if (!canUseFilePicker) return
    setFilePickerOpen(true)
    setBrowsePath(null)
  }

  const handleTextChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const nextText = event.target.value
    const typedAtTrigger = canUseFilePicker && nextText.endsWith('@') && nextText.length > text.length
    setText(nextText)
    if (typedAtTrigger) {
      setFilePickerOpen(true)
      setBrowsePath(null)
    }
  }

  const removeSelectedFile = (path: string) => {
    setSelectedFiles((current) => current.filter((file) => file.path !== path))
  }

  const addSelectedFile = (file: SelectedFileContext) => {
    setSelectedFiles((current) => {
      if (current.some((selected) => selected.path === file.path)) return current
      return [...current, file].slice(0, 20)
    })
    setText((current) => (current.endsWith('@') ? current.slice(0, -1) : current))
    setFilePickerOpen(false)
    textareaRef.current?.focus()
  }

  const submit = async (intentOverride?: SendIntent) => {
    const trimmed = text.trim()
    if (!trimmed || disabled || isSending) return
    setText('')
    setSelectedFiles([])
    setFilePickerOpen(false)
    const intent = intentOverride ?? (isReplying && canSteer ? 'steer' : 'queue')
    await onSend(trimmed, intent, localContextFromFiles(selectedFiles))
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
              'relative z-0 mx-2 mb-[-10px] rounded-t-2xl border border-input bg-background px-3 pt-2 pb-5 text-xs shadow-xs sm:mx-10 sm:rounded-t-3xl sm:px-4',
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
        {selectedFiles.length > 0 ? (
          <FileReferenceChips
            files={selectedFiles}
            onRemove={removeSelectedFile}
            className="mx-2 mb-2 sm:mx-10"
          />
        ) : null}
        {filePickerOpen ? (
          <FileContextPicker
            result={browseResult}
            loading={browseLoading}
            error={browseError}
            onClose={() => setFilePickerOpen(false)}
            onNavigate={setBrowsePath}
            onSelect={addSelectedFile}
          />
        ) : null}
        <div
          className={cn(
            'relative z-10 flex items-end gap-2 border border-input bg-background px-3 py-2 shadow-xs transition-[border-radius,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50',
            isMultiline ? 'rounded-2xl' : 'rounded-full',
          )}
        >
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={!canUseFilePicker}
            onClick={openFilePicker}
            aria-label="Add file context"
            title={canUseFilePicker ? '添加 @file 上下文' : '当前没有可浏览的工作目录'}
            className="mb-1 shrink-0 rounded-full text-muted-foreground"
          >
            <AtSignIcon className="size-4" />
          </Button>
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={handleTextChange}
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
  const selectedFiles = message.localContext?.selected_files ?? []

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
        <div className="min-w-0 flex-1">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleEditKeyDown}
            rows={Math.min(4, Math.max(1, draft.split('\n').length))}
            className="min-h-24 w-full min-w-0 resize-none rounded-xl border border-input bg-background px-2.5 py-1.5 text-xs outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 sm:min-h-8"
            autoFocus
          />
          <FileReferenceChips files={selectedFiles} compact className="mt-1" />
        </div>
        <div className="col-start-2 flex min-h-10 shrink-0 items-center justify-end gap-1 sm:col-start-auto sm:min-h-0 sm:justify-start sm:pt-0.5">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-10 rounded-full px-4 text-xs sm:h-7 sm:px-2.5"
            disabled={!draft.trim()}
            onClick={saveEdit}
          >
            保存
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-10 rounded-full px-4 text-xs sm:h-7 sm:px-2.5"
            onClick={cancelEdit}
          >
            取消
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-8 items-center gap-2">
      {queueFlushPending ? (
        <LoaderCircleIcon className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <CornerDownRightIcon className="size-3.5 shrink-0 text-muted-foreground" />
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs leading-5 text-foreground">{message.text}</div>
        <FileReferenceChips files={selectedFiles} compact className="mt-0.5" />
      </div>
      <div className="flex shrink-0 items-center gap-1 text-muted-foreground">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 rounded-full px-2 text-xs text-muted-foreground"
          disabled={!canSteer}
          onClick={onSteer}
          title="立即作为引导发送给当前任务"
        >
          <CornerDownRightIcon className="size-3.5" />
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
            className="inline-flex size-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            title="排队消息选项"
          >
            <MoreHorizontalIcon className="size-3.5" />
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

function FileContextPicker({
  result,
  loading,
  error,
  onClose,
  onNavigate,
  onSelect,
}: {
  result: WorkspaceFileBrowseResult | null
  loading: boolean
  error: string | null
  onClose: () => void
  onNavigate: (path: string | null) => void
  onSelect: (file: SelectedFileContext) => void
}) {
  const entries = result?.entries ?? []

  return (
    <div className="mx-2 mb-2 rounded-2xl border border-input bg-background p-2 text-sm shadow-lg sm:mx-10">
      <div className="flex items-center gap-2 border-b border-border/70 px-1 pb-2">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="rounded-full"
          disabled={!result?.parent || loading}
          onClick={() => onNavigate(result?.parent ?? null)}
          aria-label="Go to parent directory"
        >
          <ChevronLeftIcon className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-muted-foreground">@file</div>
          <div className="truncate text-xs text-foreground">{result?.path ?? 'Loading workspace…'}</div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="rounded-full"
          onClick={onClose}
          aria-label="Close file picker"
        >
          <XIcon className="size-4" />
        </Button>
      </div>

      {error ? (
        <div className="px-2 py-3 text-sm text-destructive">{error}</div>
      ) : loading && entries.length === 0 ? (
        <div className="flex items-center gap-2 px-2 py-3 text-muted-foreground">
          <LoaderCircleIcon className="size-4 animate-spin" />
          Loading files…
        </div>
      ) : entries.length === 0 ? (
        <div className="px-2 py-3 text-muted-foreground">No files in this directory.</div>
      ) : (
        <div className="mt-2 max-h-64 overflow-y-auto">
          {entries.map((entry) => (
            <button
              key={`${entry.kind}:${entry.path}`}
              type="button"
              className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
              onClick={() => {
                if (entry.kind === 'directory') {
                  onNavigate(entry.path)
                  return
                }
                onSelect({
                  path: entry.path,
                  workspace_relative_path: entry.workspace_relative_path,
                })
              }}
            >
              {entry.kind === 'directory' ? (
                <FolderIcon className="size-4 shrink-0 text-muted-foreground" />
              ) : (
                <FileIcon className="size-4 shrink-0 text-muted-foreground" />
              )}
              <span className="min-w-0 flex-1 truncate">{entry.name}</span>
              {entry.kind === 'directory' ? (
                <span className="text-xs text-muted-foreground">Open</span>
              ) : (
                <span className="text-xs text-muted-foreground">Select</span>
              )}
            </button>
          ))}
        </div>
      )}

      {result?.truncated ? (
        <div className="mt-2 px-2 text-xs text-muted-foreground">List truncated.</div>
      ) : null}
    </div>
  )
}

function FileReferenceChips({
  files,
  compact = false,
  className,
  onRemove,
}: {
  files: SelectedFileContext[]
  compact?: boolean
  className?: string
  onRemove?: (path: string) => void
}) {
  if (files.length === 0) return null

  return (
    <div className={cn('flex min-w-0 flex-wrap gap-1', className)}>
      {files.map((file) => (
        <span
          key={file.path}
          className={cn(
            'inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-muted text-muted-foreground',
            compact ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-1 text-xs',
          )}
          title={file.path}
        >
          <FileIcon className={compact ? 'size-3' : 'size-3.5'} />
          <span className="max-w-48 truncate">{fileLabel(file)}</span>
          {onRemove ? (
            <button
              type="button"
              className="rounded-full p-0.5 hover:bg-background hover:text-foreground"
              onClick={() => onRemove(file.path)}
              aria-label={`Remove ${fileLabel(file)}`}
            >
              <XIcon className="size-3" />
            </button>
          ) : null}
        </span>
      ))}
    </div>
  )
}

function localContextFromFiles(files: SelectedFileContext[]): LocalContext | undefined {
  return files.length > 0 ? { selected_files: files } : undefined
}

function fileLabel(file: SelectedFileContext): string {
  return file.workspace_relative_path || file.path
}

export type { ComposerMode }

export function resolveComposerMode(
  latestRunStatus: RunStatus | undefined,
  sending: boolean,
): ComposerMode {
  if (sending) return 'sending'
  if (isComposerBusy(latestRunStatus) && !isUserReplyStatus(latestRunStatus)) return 'waiting'
  if (isUserReplyStatus(latestRunStatus)) return 'replying'
  return 'idle'
}
