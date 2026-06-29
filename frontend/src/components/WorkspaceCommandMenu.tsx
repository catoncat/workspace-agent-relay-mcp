import { Command } from 'cmdk'
import { Check, Folder, FolderPlus, Search } from 'lucide-react'
import type { Workspace } from '@/api/types'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  workspaces: Workspace[]
  currentWorkspaceId: number | null
  onSelectWorkspace: (id: number | null) => void | Promise<unknown>
  onAddWorkspace?: () => void | Promise<unknown>
  addingWorkspace?: boolean
  switchingWorkspace?: boolean
}

export function WorkspaceCommandMenu({
  open,
  onOpenChange,
  workspaces,
  currentWorkspaceId,
  onSelectWorkspace,
  onAddWorkspace,
  addingWorkspace = false,
  switchingWorkspace = false,
}: Props) {
  const disabled = addingWorkspace || switchingWorkspace

  async function selectWorkspace(id: number | null) {
    if (disabled) return
    try {
      await onSelectWorkspace(id)
      onOpenChange(false)
    } catch {
      // mutation hooks surface errors to the user
    }
  }

  async function addWorkspace() {
    if (!onAddWorkspace || disabled) return
    onOpenChange(false)
    await onAddWorkspace()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden p-0 sm:max-w-lg" showCloseButton={false}>
        <DialogTitle className="sr-only">Switch directory</DialogTitle>
        <Command
          label="Switch directory"
          className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
        >
          <div className="flex h-11 items-center gap-2 border-b px-3">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <Command.Input
              autoFocus
              placeholder="Switch directory..."
              className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            <kbd className="rounded border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              esc
            </kbd>
          </div>
          <Command.List className="max-h-[360px] overflow-y-auto p-1">
            <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">
              No matching directories
            </Command.Empty>
            <Command.Group heading="Directories">
              <Command.Item
                value="none no directory wu mulu 无目录"
                disabled={disabled}
                onSelect={() => void selectWorkspace(null)}
                className={commandItemClass}
              >
                <Folder className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">无目录</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    不附带 working_directory
                  </span>
                </span>
                {currentWorkspaceId === null ? <Check className="size-4 text-primary" /> : null}
              </Command.Item>
              {workspaces.map((workspace) => (
                <Command.Item
                  key={workspace.id}
                  value={`${workspace.name} ${workspace.working_directory ?? ''}`}
                  disabled={disabled}
                  onSelect={() => void selectWorkspace(workspace.id)}
                  className={commandItemClass}
                >
                  <Folder className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{workspace.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {workspace.working_directory || 'No directory'}
                    </span>
                  </span>
                  {workspace.id === currentWorkspaceId ? (
                    <Check className="size-4 shrink-0 text-primary" />
                  ) : null}
                </Command.Item>
              ))}
            </Command.Group>
            {onAddWorkspace ? (
              <Command.Group heading="Actions">
                <Command.Item
                  value="add directory workspace folder"
                  disabled={disabled}
                  onSelect={() => void addWorkspace()}
                  className={cn(commandItemClass, 'text-primary')}
                >
                  <FolderPlus className="size-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">
                    {addingWorkspace ? 'Adding directory...' : 'Add directory...'}
                  </span>
                </Command.Item>
              </Command.Group>
            ) : null}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  )
}

const commandItemClass = cn(
  'flex cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 outline-none',
  'data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50',
  'data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground',
)
