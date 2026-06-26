import type { Agent } from '@/api/types'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  token: string
  onTokenChange: (value: string) => void
  agents: Agent[]
}

export function SettingsSheet({ open, onOpenChange, token, onTokenChange, agents }: Props) {
  const agent = agents[0]

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Settings</SheetTitle>
          <SheetDescription>
            Connection and agent configuration. The relay API token is stored in this browser only.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-6 px-4 pb-4">
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

          {agent && (
            <>
              <Separator />
              <div className="space-y-2">
                <p className="text-sm font-medium leading-none">Workspace Agent</p>
                <p className="text-sm font-medium">{agent.name}</p>
                <p className="font-mono text-xs text-muted-foreground break-all">{agent.trigger_id}</p>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
