import type { RunDetail } from '@/api/types'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronDown } from 'lucide-react'

type Props = {
  detail: RunDetail | null
}

function MetaRow({
  label,
  value,
  href,
}: {
  label: string
  value?: string | number | null
  href?: string
}) {
  const display = value ?? 'n/a'
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 text-xs">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="break-all font-mono">
        {href && value ? (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            {String(display)}
          </a>
        ) : (
          String(display)
        )}
      </dd>
    </div>
  )
}

export function RunInspector({ detail }: Props) {
  if (!detail) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-center text-sm text-muted-foreground">
          Select a run to inspect trigger metadata and callbacks.
        </p>
      </div>
    )
  }

  const run = detail.run

  return (
    <ScrollArea className="h-full">
      <div className="space-y-3 p-4">
        <Card className="gap-0 py-0">
          <CardHeader className="border-b px-4 py-3">
            <CardTitle className="text-sm">Run</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 px-4 py-3">
            <div className="grid grid-cols-[7rem_1fr] gap-2 text-xs">
              <dt className="text-muted-foreground">status</dt>
              <dd>
                <StatusBadge status={run.status} />
              </dd>
            </div>
            <MetaRow label="request_id" value={run.request_id} />
            <MetaRow label="conv_key" value={run.conversation_key} />
            <MetaRow label="created_at" value={run.created_at} />
            <MetaRow label="completed_at" value={run.completed_at} />
          </CardContent>
        </Card>

        <Card className="gap-0 py-0">
          <CardHeader className="border-b px-4 py-3">
            <CardTitle className="text-sm">Trigger (202)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 px-4 py-3">
            <MetaRow label="idem_key" value={run.idempotency_key} />
            <MetaRow label="trig_status" value={run.trigger_status} />
            <MetaRow label="http_status" value={run.trigger_http_status} />
            <MetaRow label="x_request_id" value={run.trigger_x_request_id} />
            <MetaRow label="conv_url" value={run.conversation_url} href={run.conversation_url} />
          </CardContent>
        </Card>

        {detail.artifacts.length > 0 && (
          <Card className="gap-0 py-0">
            <CardHeader className="border-b px-4 py-3">
              <CardTitle className="text-sm">Artifacts ({detail.artifacts.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 px-4 py-3">
              {detail.artifacts.map((artifact) => (
                <div key={artifact.name} className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{artifact.name}</Badge>
                    <span className="text-xs text-muted-foreground">{artifact.mime_type}</span>
                  </div>
                  <pre className="max-h-40 overflow-auto rounded-md bg-muted p-2 font-mono text-xs">
                    {artifact.content}
                  </pre>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        <Collapsible>
          <Card className="gap-0 py-0">
            <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium hover:bg-muted/50">
              Raw JSON
              <ChevronDown className="size-4 text-muted-foreground" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CardContent className="border-t px-4 py-3">
                <pre className="max-h-64 overflow-auto font-mono text-xs">
                  {JSON.stringify(detail, null, 2)}
                </pre>
              </CardContent>
            </CollapsibleContent>
          </Card>
        </Collapsible>
      </div>
    </ScrollArea>
  )
}
