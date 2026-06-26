import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from 'react'
import { ClipboardCopy, Hash, MessageSquarePlus, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Conversation } from '@/api/types'
import { Button } from '@/components/ui/button'
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
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'

type Props = {
  conversations: Conversation[]
  selectedId: number | null
  onSelect: (id: number) => void
  onNew: () => void
  onRefresh: () => void
  onRename?: (id: number, name: string) => void | Promise<unknown>
  onDelete?: (id: number) => void | Promise<unknown>
  loading?: boolean
}

export function RelaySidebar({
  conversations,
  selectedId,
  onSelect,
  onNew,
  onRefresh,
  onRename,
  onDelete,
  loading = false,
}: Props) {
  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex h-12 items-center gap-2 px-3">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary text-xs font-bold leading-none text-primary-foreground">
            AR
          </div>
          <span className="font-semibold tracking-tight">Agent Relay</span>
          <Button
            variant="ghost"
            size="icon-sm"
            className="ml-auto text-muted-foreground"
            title="Refresh conversations"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw className={loading ? 'motion-safe:animate-spin' : ''} />
          </Button>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Conversations</SidebarGroupLabel>
          <SidebarGroupAction title="New conversation" onClick={onNew}>
            <MessageSquarePlus />
            <span className="sr-only">New conversation</span>
          </SidebarGroupAction>
          <SidebarGroupContent>
            <SidebarMenu>
              {conversations.length === 0 ? (
                <SidebarMenuItem>
                  <div className="px-2 py-4 text-xs text-muted-foreground">
                    <p>{loading ? 'Loading...' : 'No conversations yet.'}</p>
                    {!loading ? (
                      <Button variant="outline" size="sm" className="mt-2 w-full" onClick={onNew}>
                        <MessageSquarePlus />
                        New conversation
                      </Button>
                    ) : null}
                  </div>
                </SidebarMenuItem>
              ) : (
                conversations.map((item) => (
                  <ConversationRow
                    key={item.id}
                    item={item}
                    isActive={item.id === selectedId}
                    onSelect={onSelect}
                    onRename={onRename}
                    onDelete={onDelete}
                  />
                ))
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}

type RowProps = {
  item: Conversation
  isActive: boolean
  onSelect: (id: number) => void
  onRename?: (id: number, name: string) => void | Promise<unknown>
  onDelete?: (id: number) => void | Promise<unknown>
}

function ConversationRow({ item, isActive, onSelect, onRename, onDelete }: RowProps) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [draftName, setDraftName] = useState(item.name)
  const inputRef = useRef<HTMLInputElement>(null)
  const deleteHintId = `delete-conversation-${item.id}-hint`

  useEffect(() => {
    if (isRenaming) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [isRenaming])

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

  const handleRowKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const key = event.key.toLowerCase()
      const modifier = event.metaKey || event.ctrlKey

      if (modifier && key === 'c') {
        event.preventDefault()
        void handleCopy(item.conversation_key, 'Continuation key')
      } else if (modifier && key === 'i') {
        event.preventDefault()
        void handleCopy(String(item.id), 'Conversation ID')
      } else if (event.key === 'F2' && onRename) {
        event.preventDefault()
        setIsRenaming(true)
      } else if ((event.key === 'Delete' || event.key === 'Backspace') && onDelete) {
        event.preventDefault()
        setDeleteOpen(true)
      }
    },
    [handleCopy, item.conversation_key, item.id, onDelete, onRename],
  )

  return (
    <SidebarMenuItem>
      <Dialog open={deleteOpen} onOpenChange={(open) => !isDeleting && setDeleteOpen(open)}>
        <ContextMenu>
          <ContextMenuTrigger render={<div className="w-full" />}>
            {isRenaming ? (
              <div className="flex items-center gap-1 px-2 py-1">
                <input
                  ref={inputRef}
                  value={draftName}
                  aria-label={`Rename ${item.name}`}
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
                  className="h-7 w-full rounded border border-input bg-background px-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/50"
                />
              </div>
            ) : (
              <SidebarMenuButton
                size="lg"
                isActive={isActive}
                onClick={() => onSelect(item.id)}
                onKeyDown={handleRowKeyDown}
                tooltip={item.name}
                aria-keyshortcuts="Control+C Meta+C Control+I Meta+I F2 Delete Backspace"
              >
                <span className="min-w-0 flex flex-col gap-0.5">
                  <span className="truncate font-medium">{item.name}</span>
                  <span className="truncate text-[11px] font-normal text-sidebar-foreground/60">
                    #{item.id}
                  </span>
                </span>
              </SidebarMenuButton>
            )}
          </ContextMenuTrigger>
          <ContextMenuContent className="w-60">
            <ContextMenuItem onClick={() => void handleCopy(item.conversation_key, 'Continuation key')}>
              <ClipboardCopy />
              <span>Copy key</span>
              <MenuShortcut>Ctrl/Cmd+C</MenuShortcut>
            </ContextMenuItem>
            <ContextMenuItem onClick={() => void handleCopy(String(item.id), 'Conversation ID')}>
              <Hash />
              <span>Copy ID</span>
              <MenuShortcut>Ctrl/Cmd+I</MenuShortcut>
            </ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem disabled={!onRename} onClick={() => setIsRenaming(true)}>
              <Pencil />
              <span>Rename</span>
              <MenuShortcut>F2</MenuShortcut>
            </ContextMenuItem>
            <ContextMenuItem
              disabled={!onDelete}
              variant="destructive"
              aria-describedby={deleteHintId}
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 />
              <span>Delete</span>
              <MenuShortcut>Del</MenuShortcut>
              <span id={deleteHintId} className="sr-only">
                Opens a confirmation dialog before deleting this conversation.
              </span>
            </ContextMenuItem>
          </ContextMenuContent>
        </ContextMenu>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              This removes "{item.name}" from the conversation list. Existing run history is archived with it.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" disabled={isDeleting} onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={!onDelete || isDeleting} onClick={() => void handleDelete()}>
              {isDeleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SidebarMenuItem>
  )
}

function MenuShortcut({ children }: { children: string }) {
  return <span className="ml-auto pl-4 text-xs text-muted-foreground">{children}</span>
}
