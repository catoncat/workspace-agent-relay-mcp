import { useCallback, useEffect, useMemo, useState } from 'react'
import { ClipboardCopy, MessageSquarePlus, Pencil, Pin, PinOff, Settings, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Agent, Conversation } from '@/api/types'
import { ThemeMenu, sidebarHeaderIconClass } from '@/components/ThemeMenu'
import { WorkingIndicator } from '@/components/WorkingIndicator'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { buildConversationKey, defaultConversationName } from '@/lib/conversationKey'
import { cn } from '@/lib/utils'

const threadButtonClass =
  'h-7 w-full rounded-md text-[13px] font-normal text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground data-active:bg-sidebar-accent data-active:font-normal data-active:text-sidebar-foreground'

const threadIndentClass = 'pl-8 pr-2'
const threadIndentSingleClass = 'pl-7 pr-2'
const threadStatusSlotClass = 'left-2'
const threadStatusSlotSingleClass = 'left-1.5'
const agentLabelClass = 'pl-2.5 pr-2 pb-0.5 text-[11px] font-normal text-muted-foreground/80'

export type CreateConversationInput = {
  agentId: number
  name: string
  key: string
}

type Props = {
  agents: Agent[]
  conversations: Conversation[]
  selectedId: number | null
  onSelect: (id: number) => void
  onCreate?: (input: CreateConversationInput) => void | Promise<unknown>
  creating?: boolean
  onRename?: (id: number, name: string) => void | Promise<unknown>
  onDelete?: (id: number) => void | Promise<unknown>
  onPin?: (id: number, pinned: boolean) => void | Promise<unknown>
  onOpenSettings?: () => void
  loading?: boolean
  workingConversationIds?: ReadonlySet<number>
}

export function RelaySidebar({
  agents,
  conversations,
  selectedId,
  onSelect,
  onCreate,
  creating = false,
  onRename,
  onDelete,
  onPin,
  onOpenSettings,
  loading = false,
  workingConversationIds,
}: Props) {
  const [isComposing, setIsComposing] = useState(false)
  const grouped = useMemo(() => groupConversations(agents, conversations), [agents, conversations])

  const handleStartCreate = useCallback(() => {
    if (!onCreate) return
    setIsComposing(true)
  }, [onCreate])

  const handleCancelCreate = useCallback(() => {
    setIsComposing(false)
  }, [])

  const handleSubmitCreate = useCallback(
    async (input: CreateConversationInput) => {
      if (!onCreate) return
      await onCreate(input)
      setIsComposing(false)
    },
    [onCreate],
  )

  return (
    <Sidebar collapsible="offcanvas" className="border-r border-sidebar-border">
      <SidebarContent className="gap-0 px-2 pb-2 pt-2">
        {onCreate ? (
          <div className="mb-1 px-0.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={creating}
              title="New thread"
              onClick={handleStartCreate}
              className="h-7 w-full cursor-pointer justify-start gap-2 px-2 text-[13px] font-normal text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
            >
              <MessageSquarePlus className="size-3.5 shrink-0 opacity-70" />
              <span>New thread</span>
            </Button>
          </div>
        ) : null}

        <SidebarGroup className="p-0">
          <SidebarGroupContent className="px-0">
            {isComposing && onCreate ? (
              <InlineCreateRow
                agents={agents}
                grouped={Boolean(grouped)}
                pending={creating}
                onCancel={handleCancelCreate}
                onSubmit={handleSubmitCreate}
              />
            ) : null}

            {conversations.length === 0 && !isComposing ? (
              <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                {loading ? 'Loading…' : 'No threads yet'}
              </p>
            ) : grouped ? (
              grouped.map((group, groupIndex) => (
                <div key={group.agent.id} className={cn('mb-1 last:mb-0', groupIndex > 0 && 'pt-1.5')}>
                  <p className={agentLabelClass}>{group.agent.name}</p>
                  <SidebarMenu className="gap-0.5">
                    {group.items.map((item) => (
                      <ConversationRow
                        key={item.id}
                        item={item}
                        isActive={item.id === selectedId}
                        isWorking={workingConversationIds?.has(item.id) ?? false}
                        indentClass={threadIndentClass}
                        statusSlotClass={threadStatusSlotClass}
                        onSelect={onSelect}
                        onRename={onRename}
                        onDelete={onDelete}
                        onPin={onPin}
                      />
                    ))}
                  </SidebarMenu>
                </div>
              ))
            ) : conversations.length > 0 ? (
              <SidebarMenu className="gap-0.5">
                {conversations.map((item) => (
                  <ConversationRow
                    key={item.id}
                    item={item}
                    isActive={item.id === selectedId}
                    isWorking={workingConversationIds?.has(item.id) ?? false}
                    indentClass={threadIndentSingleClass}
                    statusSlotClass={threadStatusSlotSingleClass}
                    onSelect={onSelect}
                    onRename={onRename}
                    onDelete={onDelete}
                    onPin={onPin}
                  />
                ))}
              </SidebarMenu>
            ) : null}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border px-2 py-2">
        <div className="flex items-center gap-0.5">
          {onOpenSettings ? (
            <Button
              variant="ghost"
              size="icon-sm"
              className={sidebarHeaderIconClass}
              title="Settings"
              onClick={onOpenSettings}
            >
              <Settings className="size-3.5" />
              <span className="sr-only">Open settings</span>
            </Button>
          ) : null}
          <ThemeMenu />
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  )
}

type InlineCreateProps = {
  agents: Agent[]
  grouped?: boolean
  pending?: boolean
  onCancel: () => void
  onSubmit: (input: CreateConversationInput) => void | Promise<unknown>
}

function InlineCreateRow({ agents, grouped = false, pending = false, onCancel, onSubmit }: InlineCreateProps) {
  const [name, setName] = useState('')
  const [agentId, setAgentId] = useState<number | null>(agents[0]?.id ?? null)
  const showAgentPicker = agents.length > 1

  useEffect(() => {
    setAgentId(agents[0]?.id ?? null)
    setName('')
  }, [agents])

  const commit = useCallback(async () => {
    const resolvedAgentId = agentId ?? agents[0]?.id
    if (!resolvedAgentId || pending) return
    const trimmed = name.trim() || defaultConversationName()
    await onSubmit({
      agentId: resolvedAgentId,
      name: trimmed,
      key: buildConversationKey(trimmed),
    })
  }, [agentId, agents, name, onSubmit, pending])

  return (
    <div className={cn('mb-1.5 space-y-2 py-1', grouped ? 'pl-3 pr-0.5' : 'px-0.5')}>
      {showAgentPicker ? (
        <div className="inline-flex max-w-full flex-wrap gap-0.5 rounded-md bg-muted/60 p-0.5">
          {agents.map((agent) => (
            <button
              key={agent.id}
              type="button"
              disabled={pending}
              onClick={() => setAgentId(agent.id)}
              onMouseDown={(event) => event.preventDefault()}
              className={cn(
                'rounded px-2 py-0.5 text-[11px] transition-colors',
                agentId === agent.id
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {agent.name}
            </button>
          ))}
        </div>
      ) : null}
      <Input
        autoFocus
        value={name}
        disabled={pending}
        placeholder="Name this thread…"
        aria-label="New thread name"
        className="h-7 border-0 bg-background/80 shadow-none focus-visible:ring-1"
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            void commit()
          } else if (event.key === 'Escape') {
            event.preventDefault()
            onCancel()
          }
        }}
        onBlur={() => {
          if (name.trim()) void commit()
          else onCancel()
        }}
      />
    </div>
  )
}

function groupConversations(
  agents: Agent[],
  conversations: Conversation[],
): Array<{ agent: Agent; items: Conversation[] }> | null {
  if (agents.length <= 1) return null
  const buckets = new Map(agents.map((agent) => [agent.id, [] as Conversation[]]))
  for (const conversation of conversations) {
    const bucket = buckets.get(conversation.agent_id)
    if (bucket) bucket.push(conversation)
  }
  return agents
    .map((agent) => ({ agent, items: buckets.get(agent.id) ?? [] }))
    .filter((group) => group.items.length > 0)
}

type RowProps = {
  item: Conversation
  isActive: boolean
  isWorking?: boolean
  indentClass: string
  statusSlotClass: string
  onSelect: (id: number) => void
  onRename?: (id: number, name: string) => void | Promise<unknown>
  onDelete?: (id: number) => void | Promise<unknown>
  onPin?: (id: number, pinned: boolean) => void | Promise<unknown>
}

function ConversationRow({
  item,
  isActive,
  isWorking = false,
  indentClass,
  statusSlotClass,
  onSelect,
  onRename,
  onDelete,
  onPin,
}: RowProps) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [draftName, setDraftName] = useState(item.name)
  const deleteHintId = `delete-conversation-${item.id}-hint`
  const displayName = item.name.trim() || 'Untitled'
  const isPinned = Boolean(item.pinned_at)

  useEffect(() => {
    setDraftName(item.name)
  }, [item.name])

  const commitRename = useCallback(async () => {
    const trimmed = draftName.trim()
    if (trimmed && trimmed !== item.name && onRename) {
      try {
        await onRename(item.id, trimmed)
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Rename failed')
        setDraftName(item.name)
      }
    } else {
      setDraftName(item.name)
    }
    setIsRenaming(false)
  }, [draftName, item.id, item.name, onRename])

  const cancelRename = useCallback(() => {
    setDraftName(item.name)
    setIsRenaming(false)
  }, [item.name])

  const handleCopy = useCallback(
    async (value: string, label: string) => {
      try {
        await navigator.clipboard.writeText(value)
        toast.success(`${label} copied`)
      } catch {
        toast.error('Clipboard unavailable')
      }
    },
    [],
  )

  const handlePin = useCallback(() => {
    if (!onPin) return
    void onPin(item.id, !isPinned)
  }, [isPinned, item.id, onPin])

  const handleDelete = useCallback(async () => {
    if (!onDelete) return
    setIsDeleting(true)
    try {
      await onDelete(item.id)
      toast.success('Conversation deleted')
      setDeleteOpen(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Delete failed')
    } finally {
      setIsDeleting(false)
    }
  }, [item.id, onDelete])

  return (
    <SidebarMenuItem>
      <Dialog open={deleteOpen} onOpenChange={(open) => !isDeleting && setDeleteOpen(open)}>
        {isRenaming ? (
          <div className={cn('py-0.5', indentClass)}>
            <Input
              autoFocus
              value={draftName}
              aria-label={`Rename ${displayName}`}
              className="h-7 border-0 bg-muted/40 shadow-none focus-visible:ring-1"
              onChange={(e) => setDraftName(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void commitRename()
                } else if (e.key === 'Escape') {
                  e.preventDefault()
                  cancelRename()
                }
              }}
            />
          </div>
        ) : (
          <ContextMenu>
            {isWorking || isPinned ? (
              <span
                className={cn(
                  'pointer-events-none absolute top-1/2 z-[1] flex size-3 -translate-y-1/2 items-center justify-center',
                  statusSlotClass,
                )}
              >
                {isWorking ? (
                  <WorkingIndicator className="text-primary" />
                ) : (
                  <Pin className="size-3 opacity-70" />
                )}
              </span>
            ) : null}
            <ContextMenuTrigger
              render={
                <SidebarMenuButton
                  isActive={isActive}
                  size="sm"
                  onClick={() => onSelect(item.id)}
                  className={cn(threadButtonClass, indentClass)}
                />
              }
            >
              <span className="truncate">{displayName}</span>
              {isWorking ? <span className="sr-only">Agent working</span> : null}
            </ContextMenuTrigger>
            <ContextMenuContent className="w-60">
              <div className="flex items-baseline justify-between gap-3 px-2 py-1.5">
                <span className="min-w-0 truncate text-sm font-medium text-foreground">{displayName}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground/70">#{item.id}</span>
              </div>
              <ContextMenuSeparator />
              <ContextMenuItem onClick={() => void handleCopy(item.conversation_key, 'Continuation key')}>
                <ClipboardCopy />
                <span>Copy key</span>
              </ContextMenuItem>
              <ContextMenuSeparator />
              <ContextMenuItem disabled={!onPin} onClick={() => void handlePin()}>
                {isPinned ? <PinOff /> : <Pin />}
                <span>{isPinned ? 'Unpin' : 'Pin'}</span>
              </ContextMenuItem>
              <ContextMenuItem disabled={!onRename} onClick={() => setIsRenaming(true)}>
                <Pencil />
                <span>Rename</span>
              </ContextMenuItem>
              <ContextMenuItem
                disabled={!onDelete}
                variant="destructive"
                aria-describedby={deleteHintId}
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 />
                <span>Delete</span>
                <span id={deleteHintId} className="sr-only">
                  Opens a confirmation dialog before deleting this conversation.
                </span>
              </ContextMenuItem>
            </ContextMenuContent>
          </ContextMenu>
        )}
        <DialogContent className="gap-3" showCloseButton={false}>
          <DialogHeader className="gap-1.5">
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              This removes "{displayName}" from the conversation list. Existing run history is archived with it.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              disabled={isDeleting}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={!onDelete || isDeleting}
              onClick={() => void handleDelete()}
            >
              {isDeleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SidebarMenuItem>
  )
}
