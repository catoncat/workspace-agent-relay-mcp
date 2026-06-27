import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Bot, ChevronDown, Info, Pencil, Plus } from 'lucide-react'
import { toast } from 'sonner'
import type { Agent, TokenRef } from '@/api/types'
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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useCreateAgent, useRenameAgent, useTokenRefs } from '@/features/relay/hooks'
import { cn } from '@/lib/utils'

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
        <TooltipProvider delay={200}>
          <SheetHeader>
            <SheetTitle>Settings</SheetTitle>
            <SheetDescription>Connect this browser and manage your agents.</SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-8 px-4 pb-8">
            <ConnectionSection token={token} onTokenChange={onTokenChange} />
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

function AgentsSection({ agents }: { agents: Agent[] }) {
  const renameAgentMutation = useRenameAgent()

  return (
    <section className="space-y-3">
      <SectionHeading
        title="Agents"
        hint="Each agent maps to a Workspace Agent trigger. Names are only for your dashboard."
      />
      {agents.length === 0 ? (
        <p className="text-sm text-muted-foreground">No agents yet. Add one below.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {agents.map((agent) => (
            <AgentRow
              key={agent.id}
              agent={agent}
              onRename={async (name) => {
                await renameAgentMutation.mutateAsync({ id: agent.id, name })
                toast.success('Agent renamed')
              }}
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
}: {
  agent: Agent
  onRename: (name: string) => void | Promise<unknown>
}) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [draftName, setDraftName] = useState(agent.name)
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

  return (
    <li className="flex items-center gap-2 px-3 py-2.5">
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
        <InfoTip>
          <div className="space-y-1.5 font-mono text-[11px] leading-relaxed">
            <p>
              <span className="text-background/70">Trigger</span>
              <br />
              {agent.trigger_id}
            </p>
            <p>
              <span className="text-background/70">URL</span>
              <br />
              {agent.trigger_url}
            </p>
            <p>
              <span className="text-background/70">Token ref</span>
              <br />
              {agent.token_ref}
            </p>
          </div>
        </InfoTip>
      </div>
    </li>
  )
}

function AddAgentSection() {
  const tokenRefsQuery = useTokenRefs()
  const createAgentMutation = useCreateAgent()
  const tokenRefs = tokenRefsQuery.data ?? []
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [triggerUrl, setTriggerUrl] = useState('')
  const [tokenRef, setTokenRef] = useState('')

  const resolvedTokenRef = tokenRef || tokenRefs[0]?.token_ref || ''
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
          toast.success('Agent added')
          setName('')
          setTriggerUrl('')
          setTokenRef('')
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
          <span className="flex-1 text-left">Add agent</span>
          <ChevronDown className="size-4 text-muted-foreground transition-transform data-panel-open:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-3">
          {tokenRefs.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No agent tokens are configured on the relay yet.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border bg-muted/20 p-3">
              <div className="space-y-2">
                <label htmlFor="agent-name" className="text-sm font-medium">
                  Name
                </label>
                <Input
                  id="agent-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Work, Personal"
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
                  <label htmlFor="agent-token-ref" className="text-sm font-medium">
                    Account
                  </label>
                  <InfoTip side="top">
                    Which server-side token should trigger this agent. Configure tokens in the
                    relay&apos;s <span className="font-mono">.env</span> and restart.
                  </InfoTip>
                </div>
                <select
                  id="agent-token-ref"
                  value={resolvedTokenRef}
                  onChange={(e) => setTokenRef(e.target.value)}
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/50"
                >
                  {tokenRefs.map((ref, index) => (
                    <option key={ref.token_ref} value={ref.token_ref}>
                      {tokenAccountLabel(ref, index)}
                    </option>
                  ))}
                </select>
              </div>

              <Button type="submit" disabled={!canSubmit} className="w-full">
                {createAgentMutation.isPending ? 'Adding...' : 'Add agent'}
              </Button>
            </form>
          )}
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

function tokenAccountLabel(ref: TokenRef, index: number): string {
  if (ref.is_default) return 'Primary account'
  const suffix = ref.env_var.replace(/^WORKSPACE_AGENT_RELAY_AGENT_TOKEN_?/, '')
  if (suffix && suffix !== ref.env_var) {
    return suffix.replace(/_/g, ' ')
  }
  return `Account ${index + 1}`
}
