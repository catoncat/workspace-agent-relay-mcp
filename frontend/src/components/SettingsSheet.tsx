import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Bot, Check, ChevronDown, Folder, Info, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Agent, RelaySettings, Workspace } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  useCreateAgent,
  useCreateWorkspace,
  useDeleteAgent,
  useDeleteWorkspace,
  useRenameAgent,
  useUpdateAgent,
  useUpdateSettings,
  useUpdateWorkspace,
} from '@/features/relay/hooks'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  token: string
  onTokenChange: (value: string) => void
  agents: Agent[]
  settings: RelaySettings
  workspaces: Workspace[]
}

export function SettingsSheet({
  open,
  onOpenChange,
  token,
  onTokenChange,
  agents,
  settings,
  workspaces,
}: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <TooltipProvider delay={200}>
          <SheetHeader>
            <SheetTitle>Settings</SheetTitle>
            <SheetDescription>Connect this browser and choose the local execution context.</SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-8 px-4 pb-8">
            <ConnectionSection token={token} onTokenChange={onTokenChange} />
            <CurrentAgentSection agents={agents} currentAgentId={settings.current_agent_id} />
            <WorkspacesSection
              workspaces={workspaces}
              currentWorkspaceId={settings.current_workspace_id}
            />
            <AgentsSection agents={agents} />
            <AddAgentSection />
          </div>
        </TooltipProvider>
      </SheetContent>
    </Sheet>
  )
}

function ConnectionSection({
  token,
  onTokenChange,
}: {
  token: string
  onTokenChange: (value: string) => void
}) {
  return (
    <section className="space-y-3">
      <SectionHeading
        title="Connection"
        hint="Matches the relay server's access password. Saved only in this browser."
      />
      <div className="space-y-2">
        <label htmlFor="relay-token" className="text-sm font-medium leading-none">
          Access password
        </label>
        <Input
          id="relay-token"
          type="password"
          value={token}
          onChange={(e) => onTokenChange(e.target.value)}
          placeholder="Enter relay password"
          autoComplete="off"
        />
      </div>
    </section>
  )
}

function CurrentAgentSection({
  agents,
  currentAgentId,
}: {
  agents: Agent[]
  currentAgentId: number | null
}) {
  const updateSettingsMutation = useUpdateSettings()

  return (
    <section className="space-y-3">
      <SectionHeading
        title="Current backend"
        hint="New threads use this Workspace Agent backend. Workspaces control the directory; this only chooses the executor."
      />
      {agents.length === 0 ? (
        <p className="text-sm text-muted-foreground">No backend configured. Add one below.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {agents.map((agent) => {
            const active = agent.id === currentAgentId
            return (
              <li key={agent.id} className="flex items-center gap-2 px-3 py-2.5">
                <Bot className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{agent.name}</span>
                {!agent.token_configured ? (
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
                    No token
                  </span>
                ) : null}
                {active ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                    <Check className="size-3" />
                    Current
                  </span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={updateSettingsMutation.isPending}
                    onClick={() =>
                      updateSettingsMutation.mutate(
                        { current_agent_id: agent.id },
                        { onSuccess: () => toast.success('Current backend updated') },
                      )
                    }
                  >
                    Use
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function WorkspacesSection({
  workspaces,
  currentWorkspaceId,
}: {
  workspaces: Workspace[]
  currentWorkspaceId: number | null
}) {
  const updateSettingsMutation = useUpdateSettings()

  return (
    <section className="space-y-3">
      <SectionHeading
        title="Workspaces"
        hint="A workspace is a named local directory. New threads inherit the current workspace; each run stores a directory snapshot."
      />
      <ul className="divide-y rounded-lg border">
        <li className="flex items-center gap-2 px-3 py-2.5">
          <Folder className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">无目录</span>
            <span className="block truncate text-xs text-muted-foreground">Do not send working_directory</span>
          </span>
          {currentWorkspaceId === null ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              <Check className="size-3" />
              Current
            </span>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={updateSettingsMutation.isPending}
              onClick={() =>
                updateSettingsMutation.mutate(
                  { current_workspace_id: null },
                  { onSuccess: () => toast.success('Workspace cleared') },
                )
              }
            >
              Use
            </Button>
          )}
        </li>
        {workspaces.map((workspace) => (
          <WorkspaceRow
            key={workspace.id}
            workspace={workspace}
            active={workspace.id === currentWorkspaceId}
          />
        ))}
      </ul>
      <AddWorkspaceSection />
    </section>
  )
}

function WorkspaceRow({ workspace, active }: { workspace: Workspace; active: boolean }) {
  const updateSettingsMutation = useUpdateSettings()
  const updateWorkspaceMutation = useUpdateWorkspace()
  const deleteWorkspaceMutation = useDeleteWorkspace()
  const [isEditing, setIsEditing] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [draftName, setDraftName] = useState(workspace.name)
  const [draftDirectory, setDraftDirectory] = useState(workspace.working_directory ?? '')

  useEffect(() => {
    setDraftName(workspace.name)
    setDraftDirectory(workspace.working_directory ?? '')
  }, [workspace.name, workspace.working_directory])

  const commitUpdate = useCallback(async () => {
    const name = draftName.trim()
    const directory = draftDirectory.trim()
    if (!name) {
      toast.error('Workspace name is required')
      return
    }
    try {
      await updateWorkspaceMutation.mutateAsync({
        id: workspace.id,
        name,
        working_directory: directory || null,
      })
      toast.success('Workspace updated')
      setIsEditing(false)
    } catch {
      // toast handled by mutation
    }
  }, [draftDirectory, draftName, updateWorkspaceMutation, workspace.id])

  const handleDelete = useCallback(async () => {
    try {
      await deleteWorkspaceMutation.mutateAsync(workspace.id)
      toast.success('Workspace deleted')
      setDeleteOpen(false)
    } catch {
      // toast handled by mutation
    }
  }, [deleteWorkspaceMutation, workspace.id])

  return (
    <li className="px-3 py-2.5">
      <Dialog
        open={deleteOpen}
        onOpenChange={(open) => !deleteWorkspaceMutation.isPending && setDeleteOpen(open)}
      >
        {isEditing ? (
          <div className="space-y-2">
            <Input
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              placeholder="Workspace name"
              autoComplete="off"
            />
            <Input
              value={draftDirectory}
              onChange={(event) => setDraftDirectory(event.target.value)}
              placeholder="/absolute/path/to/repo"
              autoComplete="off"
            />
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                disabled={updateWorkspaceMutation.isPending}
                onClick={() => void commitUpdate()}
              >
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setDraftName(workspace.name)
                  setDraftDirectory(workspace.working_directory ?? '')
                  setIsEditing(false)
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Folder className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{workspace.name}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {workspace.working_directory || 'No directory'}
              </span>
            </span>
            {active ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                <Check className="size-3" />
                Current
              </span>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={updateSettingsMutation.isPending}
                onClick={() =>
                  updateSettingsMutation.mutate(
                    { current_workspace_id: workspace.id },
                    { onSuccess: () => toast.success('Current workspace updated') },
                  )
                }
              >
                Use
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground"
              title={`Edit ${workspace.name}`}
              onClick={() => setIsEditing(true)}
            >
              <Pencil />
              <span className="sr-only">Edit {workspace.name}</span>
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground hover:text-destructive"
              title={`Delete ${workspace.name}`}
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 />
              <span className="sr-only">Delete {workspace.name}</span>
            </Button>
          </div>
        )}
        <DialogContent className="gap-3" showCloseButton={false}>
          <DialogHeader className="gap-1.5">
            <DialogTitle>Delete workspace?</DialogTitle>
            <DialogDescription>
              Threads in "{workspace.name}" move to 无目录. Existing run directory snapshots are kept.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              disabled={deleteWorkspaceMutation.isPending}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleteWorkspaceMutation.isPending}
              onClick={() => void handleDelete()}
            >
              {deleteWorkspaceMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  )
}

function AddWorkspaceSection() {
  const createWorkspaceMutation = useCreateWorkspace()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [workingDirectory, setWorkingDirectory] = useState('')

  const canSubmit =
    !createWorkspaceMutation.isPending &&
    name.trim().length > 0 &&
    workingDirectory.trim().length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    createWorkspaceMutation.mutate(
      {
        name: name.trim(),
        working_directory: workingDirectory.trim(),
      },
      {
        onSuccess: () => {
          toast.success('Workspace added')
          setName('')
          setWorkingDirectory('')
          setOpen(false)
        },
      },
    )
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        className={cn(
          'flex w-full items-center gap-2 rounded-lg border border-dashed px-3 py-2.5 text-sm font-medium transition-colors',
          'hover:bg-muted/50 data-panel-open:bg-muted/30',
        )}
      >
        <Plus className="size-4 text-muted-foreground" />
        <span className="flex-1 text-left">Add workspace</span>
        <ChevronDown className="size-4 text-muted-foreground transition-transform data-panel-open:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">
        <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border bg-muted/20 p-3">
          <div className="space-y-2">
            <label htmlFor="workspace-name" className="text-sm font-medium">
              Name
            </label>
            <Input
              id="workspace-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Relay MCP"
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="workspace-directory" className="text-sm font-medium">
              Working directory
            </label>
            <Input
              id="workspace-directory"
              value={workingDirectory}
              onChange={(e) => setWorkingDirectory(e.target.value)}
              placeholder="/Users/me/work/repo"
              autoComplete="off"
            />
          </div>
          <Button type="submit" disabled={!canSubmit} className="w-full">
            {createWorkspaceMutation.isPending ? 'Adding...' : 'Add workspace'}
          </Button>
        </form>
      </CollapsibleContent>
    </Collapsible>
  )
}

function AgentsSection({ agents }: { agents: Agent[] }) {
  const renameAgentMutation = useRenameAgent()
  const deleteAgentMutation = useDeleteAgent()

  return (
    <section className="space-y-3">
      <SectionHeading
        title="Execution backends"
        hint="Each backend maps to a Workspace Agent trigger. Names are only for your dashboard."
      />
      {agents.length === 0 ? (
        <p className="text-sm text-muted-foreground">No backends yet. Add one below.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {agents.map((agent) => (
            <AgentRow
              key={agent.id}
              agent={agent}
              onRename={async (name) => {
                await renameAgentMutation.mutateAsync({ id: agent.id, name })
                toast.success('Backend renamed')
              }}
              onDelete={async () => {
                await deleteAgentMutation.mutateAsync(agent.id)
                toast.success('Backend deleted')
              }}
              deleting={deleteAgentMutation.isPending}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function AgentRow({
  agent,
  onRename,
  onDelete,
  deleting = false,
}: {
  agent: Agent
  onRename: (name: string) => void | Promise<unknown>
  onDelete: () => void | Promise<unknown>
  deleting?: boolean
}) {
  const updateAgentMutation = useUpdateAgent()
  const [isRenaming, setIsRenaming] = useState(false)
  const [isEditingToken, setIsEditingToken] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [draftName, setDraftName] = useState(agent.name)
  const [draftToken, setDraftToken] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setDraftName(agent.name)
  }, [agent.name])

  useEffect(() => {
    if (isRenaming) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [isRenaming])

  const commitRename = useCallback(async () => {
    const trimmed = draftName.trim()
    if (!trimmed) {
      setDraftName(agent.name)
      setIsRenaming(false)
      return
    }
    if (trimmed !== agent.name) {
      try {
        await onRename(trimmed)
      } catch {
        setDraftName(agent.name)
      }
    }
    setIsRenaming(false)
  }, [agent.name, draftName, onRename])

  const commitToken = useCallback(async () => {
    const trimmed = draftToken.trim()
    if (!trimmed) {
      setIsEditingToken(false)
      setDraftToken('')
      return
    }
    try {
      await updateAgentMutation.mutateAsync({ id: agent.id, access_token: trimmed })
      toast.success('Access token saved')
      setDraftToken('')
      setIsEditingToken(false)
    } catch {
      // toast handled in mutation
    }
  }, [agent.id, draftToken, updateAgentMutation])

  const handleDelete = useCallback(async () => {
    try {
      await onDelete()
      setDeleteOpen(false)
    } catch {
      // toast handled in mutation
    }
  }, [onDelete])

  return (
    <li className="px-3 py-2.5">
      <Dialog open={deleteOpen} onOpenChange={(open) => !deleting && setDeleteOpen(open)}>
      <div className="flex items-center gap-2">
        <Bot className="size-4 shrink-0 text-muted-foreground" />
        {isRenaming ? (
          <input
            ref={inputRef}
            value={draftName}
            aria-label={`Rename ${agent.name}`}
            onChange={(e) => setDraftName(e.target.value)}
            onBlur={() => void commitRename()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                void commitRename()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                setDraftName(agent.name)
                setIsRenaming(false)
              }
            }}
            className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/50"
          />
        ) : (
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{agent.name}</span>
        )}
        <div className="flex shrink-0 items-center gap-0.5">
          {!agent.token_configured ? (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
              No token
            </span>
          ) : null}
          {!isRenaming ? (
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground"
          title={`Rename ${agent.name}`}
              onClick={() => setIsRenaming(true)}
            >
              <Pencil />
              <span className="sr-only">Rename {agent.name}</span>
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-muted-foreground hover:text-destructive"
            title={`Delete ${agent.name}`}
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 />
            <span className="sr-only">Delete {agent.name}</span>
          </Button>
          <InfoTip>
            <div className="space-y-1.5 font-mono text-[11px] leading-relaxed">
              <p>
                <span className="text-background/70">Trigger</span>
                <br />
                {agent.trigger_id || '—'}
              </p>
              <p>
                <span className="text-background/70">URL</span>
                <br />
                {agent.trigger_url || '—'}
              </p>
              <p>
                <span className="text-background/70">Token</span>
                <br />
                {agent.token_configured ? 'Configured (stored on relay)' : 'Not configured'}
              </p>
            </div>
          </InfoTip>
        </div>
      </div>
      {isEditingToken ? (
        <div className="mt-2 space-y-2 pl-6">
          <Input
            autoFocus
            type="password"
            value={draftToken}
            onChange={(e) => setDraftToken(e.target.value)}
            placeholder="Paste Workspace Agent access token"
            autoComplete="off"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                void commitToken()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                setIsEditingToken(false)
                setDraftToken('')
              }
            }}
          />
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={updateAgentMutation.isPending || !draftToken.trim()}
              onClick={() => void commitToken()}
            >
              Save token
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setIsEditingToken(false)
                setDraftToken('')
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-1.5 pl-6">
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto px-0 text-xs text-muted-foreground"
            onClick={() => setIsEditingToken(true)}
          >
            {agent.token_configured ? 'Update access token' : 'Add access token'}
          </Button>
        </div>
      )}
        <DialogContent className="gap-3" showCloseButton={false}>
          <DialogHeader className="gap-1.5">
            <DialogTitle>Delete backend?</DialogTitle>
            <DialogDescription>
              This permanently removes "{agent.name}" and all of its threads and run history from this
              relay.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              disabled={deleting}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleting}
              onClick={() => void handleDelete()}
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  )
}

function AddAgentSection() {
  const createAgentMutation = useCreateAgent()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [triggerUrl, setTriggerUrl] = useState('')
  const [accessToken, setAccessToken] = useState('')

  const canSubmit =
    !createAgentMutation.isPending &&
    name.trim().length > 0 &&
    triggerUrl.trim().length > 0 &&
    accessToken.trim().length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    createAgentMutation.mutate(
      {
        name: name.trim(),
        trigger_url: triggerUrl.trim(),
        access_token: accessToken.trim(),
      },
      {
        onSuccess: () => {
          toast.success('Agent added')
          setName('')
          setTriggerUrl('')
          setAccessToken('')
          setOpen(false)
        },
      },
    )
  }

  return (
    <section>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger
          className={cn(
            'flex w-full items-center gap-2 rounded-lg border border-dashed px-3 py-2.5 text-sm font-medium transition-colors',
            'hover:bg-muted/50 data-panel-open:bg-muted/30',
          )}
        >
          <Plus className="size-4 text-muted-foreground" />
          <span className="flex-1 text-left">Add backend</span>
          <ChevronDown className="size-4 text-muted-foreground transition-transform data-panel-open:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border bg-muted/20 p-3">
            <div className="space-y-2">
              <label htmlFor="agent-name" className="text-sm font-medium">
                Name
              </label>
              <Input
                id="agent-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Work backend"
                autoComplete="off"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5">
                <label htmlFor="agent-trigger-url" className="text-sm font-medium">
                  Trigger URL
                </label>
                <InfoTip side="top">
                  Paste the trigger URL from your Workspace Agent settings in ChatGPT.
                </InfoTip>
              </div>
              <Input
                id="agent-trigger-url"
                value={triggerUrl}
                onChange={(e) => setTriggerUrl(e.target.value)}
                placeholder="https://api.chatgpt.com/v1/workspace_agents/…/trigger"
                autoComplete="off"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-1.5">
                <label htmlFor="agent-access-token" className="text-sm font-medium">
                  Access token
                </label>
                <InfoTip side="top">
                  From the same Workspace Agent settings page in ChatGPT. Stored on this relay only;
                  never sent back to the browser after save.
                </InfoTip>
              </div>
              <Input
                id="agent-access-token"
                type="password"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                placeholder="at-…"
                autoComplete="off"
              />
            </div>

            <Button type="submit" disabled={!canSubmit} className="w-full">
              {createAgentMutation.isPending ? 'Adding...' : 'Add backend'}
            </Button>
          </form>
        </CollapsibleContent>
      </Collapsible>
    </section>
  )
}

function SectionHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <h2 className="text-sm font-semibold">{title}</h2>
      <InfoTip side="top">{hint}</InfoTip>
    </div>
  )
}

function InfoTip({
  children,
  side = 'left',
}: {
  children: ReactNode
  side?: 'top' | 'left' | 'right' | 'bottom'
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="size-7 text-muted-foreground hover:text-foreground"
          >
            <Info className="size-3.5" />
            <span className="sr-only">More info</span>
          </Button>
        }
      />
      <TooltipContent side={side} className="max-w-xs text-left font-sans">
        {children}
      </TooltipContent>
    </Tooltip>
  )
}
