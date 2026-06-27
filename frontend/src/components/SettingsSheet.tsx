import { useState } from 'react'
import type { FormEvent } from 'react'
import { Bot, Plus } from 'lucide-react'
import { toast } from 'sonner'
import type { Agent } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'
import { useCreateAgent, useTokenRefs } from '@/features/relay/hooks'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  token: string
  onTokenChange: (value: string) => void
  agents: Agent[]
}

export function SettingsSheet({ open, onOpenChange, token, onTokenChange, agents }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Settings</SheetTitle>
          <SheetDescription>
            Connection and agent configuration. The relay API token is stored in this browser only.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-6 px-4 pb-8">
          <RelayTokenSection token={token} onTokenChange={onTokenChange} />
          <Separator />
          <AgentsSection agents={agents} />
          <Separator />
          <CreateAgentSection />
        </div>
      </SheetContent>
    </Sheet>
  )
}

function RelayTokenSection({
  token,
  onTokenChange,
}: {
  token: string
  onTokenChange: (value: string) => void
}) {
  return (
    <div className="space-y-2">
      <label htmlFor="relay-token" className="text-sm font-medium leading-none">
        Relay API Token
      </label>
      <Input
        id="relay-token"
        type="password"
        value={token}
        onChange={(e) => onTokenChange(e.target.value)}
        placeholder="WORKSPACE_AGENT_RELAY_AUTH_TOKEN"
        autoComplete="off"
      />
      <p className="text-xs text-muted-foreground">
        Maps to <code className="font-mono">WORKSPACE_AGENT_RELAY_AUTH_TOKEN</code> on the server.
      </p>
    </div>
  )
}

function AgentsSection({ agents }: { agents: Agent[] }) {
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium leading-none">Workspace Agents</p>
      {agents.length === 0 ? (
        <p className="text-xs text-muted-foreground">No agents registered yet.</p>
      ) : (
        <ul className="space-y-2">
          {agents.map((agent) => (
            <li key={agent.id} className="rounded-md border bg-muted/20 p-2">
              <div className="flex items-center gap-2">
                <Bot className="size-3.5 text-muted-foreground" />
                <span className="text-sm font-medium">{agent.name}</span>
              </div>
              <p className="mt-1 font-mono text-[11px] break-all text-muted-foreground">
                {agent.trigger_id}
              </p>
              <p className="mt-0.5 font-mono text-[11px] text-muted-foreground/70">
                {agent.token_ref}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function CreateAgentSection() {
  const tokenRefsQuery = useTokenRefs()
  const createAgentMutation = useCreateAgent()
  const tokenRefs = tokenRefsQuery.data ?? []

  const [name, setName] = useState('')
  const [triggerUrl, setTriggerUrl] = useState('')
  const [tokenRef, setTokenRef] = useState('')

  const resolvedTokenRef = tokenRef || tokenRefs[0]?.token_ref || ''
  const triggerId = parseTriggerId(triggerUrl)
  const namePlaceholder = triggerId ? `Agent ${triggerId.slice(-4)}` : 'Agent name'
  const canSubmit =
    !createAgentMutation.isPending &&
    name.trim().length > 0 &&
    triggerUrl.trim().length > 0 &&
    resolvedTokenRef.length > 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    createAgentMutation.mutate(
      { name: name.trim(), trigger_url: triggerUrl.trim(), token_ref: resolvedTokenRef },
      {
        onSuccess: () => {
          toast.success('Agent registered')
          setName('')
          setTriggerUrl('')
          setTokenRef('')
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex items-center gap-2">
        <Plus className="size-4 text-muted-foreground" />
        <p className="text-sm font-medium leading-none">Register another agent</p>
      </div>
      <p className="text-xs text-muted-foreground">
        Add a Workspace Agent from another ChatGPT account. Its access token must already be set in
        the relay's <code className="font-mono">.env</code> as a{' '}
        <code className="font-mono">WORKSPACE_AGENT_RELAY_AGENT_TOKEN_*</code> var, then select that
        var here.
      </p>

      <div className="space-y-2">
        <label htmlFor="agent-name" className="text-xs font-medium">
          Display name
        </label>
        <Input
          id="agent-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={namePlaceholder}
          autoComplete="off"
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="agent-trigger-url" className="text-xs font-medium">
          Trigger URL
        </label>
        <Input
          id="agent-trigger-url"
          value={triggerUrl}
          onChange={(e) => setTriggerUrl(e.target.value)}
          placeholder="https://api.chatgpt.com/v1/workspace_agents/agtch_.../trigger"
          autoComplete="off"
          className="font-mono text-xs"
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="agent-token-ref" className="text-xs font-medium">
          Token (env var)
        </label>
        {tokenRefs.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No tokens configured on the relay. Set a{' '}
            <code className="font-mono">WORKSPACE_AGENT_RELAY_AGENT_TOKEN_*</code> var in{' '}
            <code className="font-mono">.env</code> and restart the relay.
          </p>
        ) : (
          <select
            id="agent-token-ref"
            value={resolvedTokenRef}
            onChange={(e) => setTokenRef(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 font-mono text-xs outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/50"
          >
            {tokenRefs.map((ref) => (
              <option key={ref.token_ref} value={ref.token_ref}>
                {ref.env_var}
                {ref.is_default ? ' (default)' : ''}
              </option>
            ))}
          </select>
        )}
      </div>

      <Button type="submit" disabled={!canSubmit} className="w-full">
        {createAgentMutation.isPending ? 'Registering...' : 'Register agent'}
      </Button>
    </form>
  )
}

function parseTriggerId(triggerUrl: string): string {
  const match = triggerUrl.match(/\/workspace_agents\/([^/]+)\/trigger$/)
  return match ? match[1] : ''
}
