import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
import {
  Message,
  MessageContent,
  MessageResponse,
} from '@/components/ai-elements/message'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import type { JsonValue, RunDetail, RunEvent, RunEventPayload } from '@/api/types'

const ACTIVE_STATUSES = new Set(['pending', 'running', 'accepted', 'waiting', 'needs_user'])
const TERMINAL_STATUSES = new Set(['done', 'blocked', 'failed'])

type Props = {
  details: RunDetail[]
}

export function ThreadView({ details }: Props) {
  if (details.length === 0) {
    return (
      <Conversation className="h-full">
        <ConversationEmptyState
          title="No runs yet"
          description="Send a task below to trigger the Workspace Agent."
        />
      </Conversation>
    )
  }

  return (
    <Conversation className="h-full">
      <ConversationContent className="mx-auto max-w-3xl gap-6">
        {[...details].reverse().map((detail) => {
          const run = detail.run
          const hint = phaseHint(detail)
          const isActive = ACTIVE_STATUSES.has(run.status)
          const hasResultEvent = detail.events.some((event) => event.event_type === 'result')

          return (
            <div key={run.id} className="flex flex-col gap-3">
              <Message from="user">
                <MessageContent>
                  <MessageResponse>{run.input_markdown || '(empty message)'}</MessageResponse>
                </MessageContent>
              </Message>

              {hint && (
                <Message from="assistant">
                  <MessageContent>
                    {isActive ? (
                      <Shimmer className="text-sm" duration={1.5}>
                        {hint}
                      </Shimmer>
                    ) : (
                      <p className="text-sm text-muted-foreground">{hint}</p>
                    )}
                  </MessageContent>
                </Message>
              )}

              {detail.events.map((event, index) => (
                <RunEventView
                  key={`${event.event_type}-${event.id ?? index}`}
                  event={event}
                  runStatus={run.status}
                />
              ))}

              {!hasResultEvent && TERMINAL_STATUSES.has(run.status) ? (
                <TerminalStatus status={run.status} />
              ) : null}

              {detail.artifacts.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pl-1">
                  {detail.artifacts.map((artifact) => (
                    <Badge key={artifact.name} variant="outline">
                      {artifact.name}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

function RunEventView({ event, runStatus }: { event: RunEvent; runStatus: string }) {
  if (event.event_type === 'progress') {
    return (
      <Tool defaultOpen className="w-full max-w-none">
        <ToolHeader
          type="dynamic-tool"
          state={eventToolState(event, runStatus)}
          toolName={event.title || event.event_type}
          title={event.title || event.event_type}
        />
        <ToolContent>
          {event.markdown ? <MessageResponse>{event.markdown}</MessageResponse> : null}
        </ToolContent>
      </Tool>
    )
  }

  if (event.event_type === 'question') return <QuestionEvent event={event} />
  if (event.event_type === 'result') return <ResultEvent event={event} runStatus={runStatus} />

  return (
    <Message from="assistant">
      <MessageContent>
        {event.title ? (
          <p className="mb-1 text-xs font-medium text-muted-foreground">{event.title}</p>
        ) : null}
        {event.markdown ? <MessageResponse>{event.markdown}</MessageResponse> : null}
      </MessageContent>
    </Message>
  )
}

function QuestionEvent({ event }: { event: RunEvent }) {
  const payload = eventPayload(event)
  const choices = stringArray(payload.choices)
  const context = stringValue(payload.context)

  return (
    <Message from="assistant">
      <MessageContent>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status="needs_user" />
            <span className="text-xs font-medium text-muted-foreground">
              {event.title || 'User input needed'}
            </span>
          </div>
          {event.markdown ? <MessageResponse>{event.markdown}</MessageResponse> : null}
          {context ? <p className="text-sm text-muted-foreground">{context}</p> : null}
          {choices.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {choices.map((choice) => (
                <Badge key={choice} variant="secondary" className="max-w-full whitespace-normal">
                  {choice}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      </MessageContent>
    </Message>
  )
}

function ResultEvent({ event, runStatus }: { event: RunEvent; runStatus: string }) {
  const payload = eventPayload(event)
  const status = stringValue(payload.status) || runStatus

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <StatusBadge status={status} />
        <span className="text-xs font-medium text-muted-foreground">
          {event.title || 'Run result'}
        </span>
      </div>
      {event.markdown ? <MessageResponse>{event.markdown}</MessageResponse> : null}
    </div>
  )
}

function TerminalStatus({ status }: { status: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
      <StatusBadge status={status} />
      <span>Run finished without a result event.</span>
    </div>
  )
}

function phaseHint(detail: RunDetail): string | null {
  const run = detail.run
  if (detail.events.length > 0) return null
  if (run.trigger_status === 'failed' || run.status === 'failed') {
    return 'Trigger failed. Open trigger trace for details.'
  }
  if (run.trigger_status === 'accepted') {
    return 'Trigger accepted (202). Waiting for the agent to call back via MCP.'
  }
  return `Trigger ${run.trigger_status || run.status || 'pending'}. Waiting for callback events.`
}

function eventToolState(
  event: RunEvent,
  runStatus: string,
): 'input-available' | 'output-available' {
  if (event.event_type === 'result') return 'output-available'
  if (ACTIVE_STATUSES.has(runStatus)) return 'input-available'
  return 'output-available'
}

function eventPayload(event: RunEvent): RunEventPayload {
  if (event.payload) return event.payload
  if (!event.payload_json) return {}
  try {
    const parsed = JSON.parse(event.payload_json) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as RunEventPayload
    }
  } catch {
    return {}
  }
  return {}
}

function stringArray(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

function stringValue(value: JsonValue | undefined): string {
  return typeof value === 'string' ? value : ''
}
