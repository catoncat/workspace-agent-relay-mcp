import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Bot, Check, KeyRound, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Agent, RelaySettings } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  useCreateAgent,
  useDeleteAgent,
  useRenameAgent,
  useUpdateAgent,
  useUpdateSettings,
} from '@/features/relay/hooks'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  token: string
  onTokenChange: (value: string) => void
  agents: Agent[]
  settings: RelaySettings
}

type SettingsPanel = 'connection' | 'agents'

const PANELS: Array<{ id: SettingsPanel; label: string }> = [
  { id: 'connection', label: 'Connection' },
  { id: 'agents', label: 'Agents' },
]

export function SettingsSheet({
  open,
  onOpenChange,
  token,
  onTokenChange,
  agents,
  settings,
}: Props) {
  const [activePanel, setActivePanel] = useState<SettingsPanel>('agents')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(720px,calc(100svh-1rem))] w-[min(760px,calc(100vw-1rem))] max-w-none flex-col overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-4 py-3 pr-11 sm:px-5">
          <DialogTitle className="text-base">Settings</DialogTitle>
          <DialogDescription className="sr-only">Workspace Agent Relay settings</DialogDescription>
        </DialogHeader>

        <div className="border-b px-3 py-2 sm:px-4">
          <div className="grid grid-cols-2 rounded-lg bg-muted p-1">
            {PANELS.map((panel) => (
              <button
                key={panel.id}
                type="button"
                onClick={() => setActivePanel(panel.id)}
                className={cn(
                  'h-8 rounded-md text-sm font-medium transition-colors',
                  activePanel === panel.id
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {panel.label}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {activePanel === 'connection' ? (
            <ConnectionPanel token={token} onTokenChange={onTokenChange} />
          ) : (
            <AgentsPanel agents={agents} currentAgentId={settings.current_agent_id} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ConnectionPanel({
  token,
  onTokenChange,
}: {
  token: string
  onTokenChange: (value: string) => void
}) {
  return (
    <div className="mx-auto w-full max-w-xl p-4 sm:p-6">
      <div className="space-y-2">
        <label htmlFor="relay-token" className="flex items-center gap-2 text-sm font-medium">
          <KeyRound className="size-4 text-muted-foreground" />
          Access password
        </label>
        <Input
          id="relay-token"
          type="password"
          value={token}
          onChange={(event) => onTokenChange(event.target.value)}
          placeholder="Enter relay password"
          autoComplete="off"
        />
      </div>
    </div>
  )
}

function AgentsPanel({ agents, currentAgentId }: { agents: Agent[]; currentAgentId: number | null }) {
  const [addOpen, setAddOpen] = useState(false)

  return (
    <div className="p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">{agents.length} configured</div>
        <Button type="button" size="sm" onClick={() => setAddOpen(true)}>
          <Plus />
          Add agent
        </Button>
      </div>

      {agents.length === 0 ? (
        <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-center">
          <Bot className="size-5 text-muted-foreground" />
          <Button type="button" size="sm" onClick={() => setAddOpen(true)}>
            <Plus />
            Add agent
          </Button>
        </div>
      ) : (
        <ul className="divide-y rounded-lg border bg-background">
          {agents.map((agent) => (
            <AgentRow key={agent.id} agent={agent} current={agent.id === currentAgentId} />
          ))}
        </ul>
      )}

      <AddAgentDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}

function AgentRow({ agent, current }: { agent: Agent; current: boolean }) {
  const renameAgentMutation = useRenameAgent()
  const updateAgentMutation = useUpdateAgent()
  const updateSettingsMutation = useUpdateSettings()
  const deleteAgentMutation = useDeleteAgent()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [name, setName] = useState(agent.name)
  const [accessToken, setAccessToken] = useState('')

  useEffect(() => {
    setName(agent.name)
    setAccessToken('')
  }, [agent.id, agent.name])

  const canSaveName = name.trim().length > 0 && name.trim() !== agent.name && !renameAgentMutation.isPending
  const canSaveToken = accessToken.trim().length > 0 && !updateAgentMutation.isPending

  async function handleUseCurrent() {
    try {
      await updateSettingsMutation.mutateAsync({ current_agent_id: agent.id })
      toast.success('Current agent updated')
    } catch {
      // toast handled in mutation
    }
  }

  async function handleSaveName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSaveName) return
    try {
      await renameAgentMutation.mutateAsync({ id: agent.id, name: name.trim() })
      toast.success('Agent renamed')
    } catch {
      setName(agent.name)
    }
  }

  async function handleSaveToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSaveToken) return
    try {
      await updateAgentMutation.mutateAsync({ id: agent.id, access_token: accessToken.trim() })
      setAccessToken('')
      toast.success('Access token saved')
    } catch {
      // toast handled in mutation
    }
  }

  async function handleDelete() {
    try {
      await deleteAgentMutation.mutateAsync(agent.id)
      toast.success('Agent deleted')
      setDeleteOpen(false)
    } catch {
      // toast handled in mutation
    }
  }

  return (
    <li className="p-3 sm:p-4">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Bot className="size-4" />
        </span>

        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium">{agent.name}</span>
                {current ? <StatusPill tone="primary">Current</StatusPill> : null}
                {!agent.token_configured ? <StatusPill tone="warning">No token</StatusPill> : null}
              </div>
              <div className="truncate text-xs text-muted-foreground">{agent.trigger_id || 'No trigger id'}</div>
            </div>
            {!current ? (
              <Button type="button" size="sm" variant="outline" disabled={updateSettingsMutation.isPending} onClick={() => void handleUseCurrent()}>
                <Check />
                Use
              </Button>
            ) : null}
            <Button type="button" size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={() => setDeleteOpen(true)}>
              <Trash2 />
              <span className="sr-only">Delete {agent.name}</span>
            </Button>
          </div>

          <form onSubmit={handleSaveName} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <Input value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" aria-label={`Name for ${agent.name}`} />
            <Button type="submit" variant="outline" disabled={!canSaveName} className="sm:w-20">
              Save
            </Button>
          </form>

          <div className="truncate rounded-md bg-muted/40 px-2.5 py-1.5 font-mono text-xs text-muted-foreground">
            {agent.trigger_url || 'No trigger URL'}
          </div>

          <form onSubmit={handleSaveToken} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <Input
              type="password"
              value={accessToken}
              onChange={(event) => setAccessToken(event.target.value)}
              placeholder={agent.token_configured ? 'Replace access token' : 'Paste access token'}
              autoComplete="off"
              aria-label={`Access token for ${agent.name}`}
            />
            <Button type="submit" variant="outline" disabled={!canSaveToken} className="sm:w-20">
              Save
            </Button>
          </form>
        </div>
      </div>

      <Dialog open={deleteOpen} onOpenChange={(value) => !deleteAgentMutation.isPending && setDeleteOpen(value)}>
        <DialogContent className="gap-3" showCloseButton={false}>
          <DialogHeader className="gap-1.5">
            <DialogTitle>Delete agent?</DialogTitle>
            <DialogDescription>This removes "{agent.name}" from this relay.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" disabled={deleteAgentMutation.isPending} onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" disabled={deleteAgentMutation.isPending} onClick={() => void handleDelete()}>
              {deleteAgentMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  )
}

function AddAgentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const createAgentMutation = useCreateAgent()
  const [name, setName] = useState('')
  const [triggerUrl, setTriggerUrl] = useState('')
  const [accessToken, setAccessToken] = useState('')

  const canSubmit =
    !createAgentMutation.isPending &&
    name.trim().length > 0 &&
    triggerUrl.trim().length > 0 &&
    accessToken.trim().length > 0

  function reset() {
    setName('')
    setTriggerUrl('')
    setAccessToken('')
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    try {
      await createAgentMutation.mutateAsync({
        name: name.trim(),
        trigger_url: triggerUrl.trim(),
        access_token: accessToken.trim(),
      })
      toast.success('Agent added')
      reset()
      onOpenChange(false)
    } catch {
      // toast handled in mutation
    }
  }

  return (
    <Dialog open={open} onOpenChange={(value) => !createAgentMutation.isPending && onOpenChange(value)}>
      <DialogContent className="w-[min(440px,calc(100vw-1rem))] gap-4">
        <DialogHeader className="gap-1.5">
          <DialogTitle>Add agent</DialogTitle>
          <DialogDescription className="sr-only">Add Workspace Agent connection</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-2">
            <label htmlFor="agent-name" className="text-sm font-medium">
              Name
            </label>
            <Input id="agent-name" value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" />
          </div>
          <div className="space-y-2">
            <label htmlFor="agent-trigger-url" className="text-sm font-medium">
              Trigger URL
            </label>
            <Input id="agent-trigger-url" value={triggerUrl} onChange={(event) => setTriggerUrl(event.target.value)} autoComplete="off" />
          </div>
          <div className="space-y-2">
            <label htmlFor="agent-access-token" className="text-sm font-medium">
              Access token
            </label>
            <Input
              id="agent-access-token"
              type="password"
              value={accessToken}
              onChange={(event) => setAccessToken(event.target.value)}
              autoComplete="off"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={createAgentMutation.isPending}
              onClick={() => {
                reset()
                onOpenChange(false)
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {createAgentMutation.isPending ? 'Adding...' : 'Add'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function StatusPill({ children, tone }: { children: string; tone: 'primary' | 'warning' }) {
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[11px] font-medium',
        tone === 'primary'
          ? 'bg-primary/10 text-primary'
          : 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
      )}
    >
      {children}
    </span>
  )
}
