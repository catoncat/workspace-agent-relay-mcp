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
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { JsonValue, Plan, PlanStep, PlanStepStatus, Run, RunDetail, RunEvent, RunEventPayload, ToolTraceFields } from '@/api/types'
import {
  CheckIcon,
  ChevronDownIcon,
  CircleIcon,
  ClockIcon,
  LoaderCircleIcon,
  MinusIcon,
  WrenchIcon,
  XCircleIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'

const ACTIVE_STATUSES = new Set(['pending', 'running', 'accepted', 'waiting', 'needs_user', 'trigger_failed'])
const TERMINAL_STATUSES = new Set(['done', 'blocked', 'failed'])

type Props = {
  details: RunDetail[]
  loading?: boolean
  onSend?: (text: string) => void | Promise<void>
  activeDetail?: RunDetail | null
}

export function ThreadView({ details, loading = false, onSend, activeDetail }: Props) {
  if (loading) {
    return (
      <Conversation className="h-full">
        <ConversationContent className="mx-auto max-w-3xl gap-6">
          <ThreadLoadingSkeleton />
        </ConversationContent>
      </Conversation>
    )
  }

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
        {activeDetail ? <StickyPlanBar detail={activeDetail} /> : null}
        {details.map((detail) => (
          <RunThread key={detail.run.id} detail={detail} onSend={onSend} />
        ))}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

function RunThread({ detail, onSend }: { detail: RunDetail; onSend?: (text: string) => void | Promise<void> }) {
  const run = detail.run
  const isActive = ACTIVE_STATUSES.has(run.status)
  const hasResultEvent = detail.events.some((event) => event.event_type === 'result')
  const progressEvents = detail.events.filter(
    (event) => event.event_type === 'progress' && (event.markdown || event.title),
  )
  const traceEvents = useMemo(
    () => progressEvents.filter((event) => isTraceEvent(event)),
    [progressEvents],
  )
  const narrationEvents = useMemo(
    () => progressEvents.filter((event) => !isTraceEvent(event)),
    [progressEvents],
  )
  const hasTraces = traceEvents.length > 0
  const hasNarrations = narrationEvents.length > 0
  // While the run is actively working and the agent hasn't added any narration
  // yet, keep traces expanded so the operator can watch tool calls stream in.
  // Once narrations land or the run finishes, collapse traces to keep focus on
  // the higher-signal notes / result.
  const tracesDefaultOpen = isActive && !hasNarrations && !hasResultEvent

  return (
    <div id={`run-${run.id}`} className="flex flex-col gap-3 scroll-mt-16">
      <Message from="user">
        <MessageContent>
          <MessageResponse>{run.input_markdown || '(empty message)'}</MessageResponse>
        </MessageContent>
      </Message>

      {detail.plan ? <PlanChecklist plan={detail.plan} active={isActive} /> : null}

      <RunPhaseHint detail={detail} />

      {hasTraces ? (
        <ToolTraceList events={traceEvents} defaultOpen={tracesDefaultOpen} />
      ) : null}

      {hasNarrations ? (
        <ProgressLog
          events={narrationEvents}
          active={isActive}
          label={hasTraces ? 'Notes' : undefined}
        />
      ) : null}

      {detail.events
        .filter((event) => event.event_type === 'question')
        .map((event, index) => (
          <QuestionEvent
            key={`question-${event.id ?? index}`}
            event={event}
            runStatus={run.status}
            onSend={onSend}
          />
        ))}

      {detail.events
        .filter((event) => event.event_type === 'result')
        .map((event, index) => (
          <ResultEvent
            key={`result-${event.id ?? index}`}
            event={event}
            runStatus={run.status}
          />
        ))}

      {!hasResultEvent && TERMINAL_STATUSES.has(run.status) ? (
        <TerminalStatus run={run} />
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
}

function planProgress(plan: Plan) {
  const total = plan.steps.length
  const doneCount = plan.steps.filter((step) => step.status === 'done').length
  const inProgress = plan.steps.some((step) => step.status === 'in_progress')
  const allDone = doneCount === total && total > 0
  const currentStep =
    plan.steps.find((step) => step.status === 'in_progress') ??
    plan.steps[plan.steps.length - 1]
  return { total, doneCount, inProgress, allDone, currentStep }
}

/** Pick the most recent run that is still active and has a plan, for the sticky
 * summary bar. Returns null when nothing is active or no active run has a plan. */
export function pickActiveRunDetail(details: RunDetail[]): RunDetail | null {
  for (let i = details.length - 1; i >= 0; i -= 1) {
    const detail = details[i]
    if (ACTIVE_STATUSES.has(detail.run.status) && detail.plan) return detail
  }
  return null
}

function PlanChecklist({ plan, active }: { plan: Plan; active: boolean }) {
  const { doneCount, inProgress, total, allDone } = planProgress(plan)

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span>Plan</span>
        <span className="tabular-nums">
          {doneCount}/{total}
        </span>
        {active && inProgress && !allDone ? (
          <span className="flex items-center gap-1 text-foreground">
            <LoaderCircleIcon className="size-3 animate-spin" />
            <span className="text-[11px]">working</span>
          </span>
        ) : null}
      </div>
      <ol className="space-y-1.5">
        {plan.steps.map((step, index) => (
          <PlanStepRow
            key={step.id}
            step={step}
            staggered={active}
            delayMs={index * 80}
          />
        ))}
      </ol>
    </div>
  )
}

function StickyPlanBar({ detail }: { detail: RunDetail }) {
  const run = detail.run
  const plan = detail.plan
  if (!plan) return null
  const { doneCount, total, inProgress, currentStep } = planProgress(plan)
  const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0

  const handleClick = () => {
    const el = document.getElementById(`run-${run.id}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="sticky top-0 z-10 flex w-full items-center gap-3 rounded-lg border bg-background/95 px-3 py-2 text-left text-sm shadow-sm backdrop-blur transition-colors hover:bg-accent/40"
    >
      <span className="shrink-0 font-medium text-muted-foreground">
        Plan <span className="tabular-nums text-foreground">{doneCount}/{total}</span>
      </span>
      <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-primary transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
        {currentStep ? currentStep.title : 'Working…'}
      </span>
      {inProgress ? (
        <LoaderCircleIcon className="size-3.5 shrink-0 animate-spin text-foreground" />
      ) : null}
    </button>
  )
}

function PlanStepRow({ step, staggered, delayMs }: { step: PlanStep; staggered: boolean; delayMs: number }) {
  const { icon, className } = stepVisual(step.status)
  return (
    <li className="flex items-start gap-2.5 text-sm">
      <span
        className={cn('mt-0.5 flex size-4 shrink-0 items-center justify-center transition-all', className)}
        style={staggered ? { transitionDelay: `${delayMs}ms` } : undefined}
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <span
          className={cn(
            'transition-colors',
            step.status === 'done' && 'text-muted-foreground line-through decoration-muted-foreground/40',
            step.status === 'skipped' && 'text-muted-foreground/60 line-through',
            step.status === 'pending' && 'text-foreground/80',
            step.status === 'in_progress' && 'text-foreground',
          )}
        >
          {step.title}
        </span>
        {step.note ? (
          <p className="mt-0.5 text-xs text-muted-foreground">{step.note}</p>
        ) : null}
      </div>
    </li>
  )
}

function stepVisual(status: PlanStepStatus): { icon: React.ReactNode; className: string } {
  switch (status) {
    case 'done':
      return {
        icon: <CheckIcon className="size-3.5 text-green-600 dark:text-green-500" />,
        className: 'scale-100',
      }
    case 'in_progress':
      return {
        icon: <LoaderCircleIcon className="size-3.5 animate-spin text-foreground" />,
        className: 'scale-100',
      }
    case 'skipped':
      return {
        icon: <MinusIcon className="size-3.5 text-muted-foreground" />,
        className: 'scale-100',
      }
    default:
      return {
        icon: <CircleIcon className="size-3 text-muted-foreground/50" />,
        className: 'scale-100',
      }
  }
}

function RunPhaseHint({ detail }: { detail: RunDetail }) {
  const run = detail.run
  const hint = phaseHint(detail)
  if (!hint) return null
  const isActive = ACTIVE_STATUSES.has(run.status)
  return (
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
  )
}

function ProgressLog({
  events,
  active,
  label,
}: {
  events: RunEvent[]
  active: boolean
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const latest = events[events.length - 1]
  const resolvedLabel = label ?? (active ? 'Working…' : 'Work log')

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="not-prose">
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md border bg-muted/20 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground">
        <span>{resolvedLabel}</span>
        <span className="truncate text-foreground/70">{latest?.title || latest?.markdown?.slice(0, 60) || ''}</span>
        <ChevronDownIcon className={cn('ml-auto size-3.5 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1.5 space-y-2 border-l-2 border-border pl-3">
          {events.map((event, index) => (
            <div key={`prog-${event.id ?? index}`} className="text-sm">
              {event.title ? (
                <p className="text-xs font-medium text-muted-foreground">{event.title}</p>
              ) : null}
              {event.markdown ? (
                <MessageResponse className="text-sm text-muted-foreground">
                  {event.markdown}
                </MessageResponse>
              ) : null}
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function ToolTraceList({
  events,
  defaultOpen,
}: {
  events: RunEvent[]
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="not-prose">
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md border bg-muted/20 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground">
        <WrenchIcon className="size-3.5" />
        <span>Tool calls</span>
        <span className="tabular-nums text-foreground/60">· {events.length}</span>
        <ChevronDownIcon className={cn('ml-auto size-3.5 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-1.5 space-y-1.5">
          {events.map((event, index) => (
            <ToolTraceRow key={`trace-${event.id ?? index}`} event={event} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function ToolTraceRow({ event }: { event: RunEvent }) {
  const [open, setOpen] = useState(false)
  const fields = traceFields(event)
  const ok = fields.ok
  const label = fields.title || fields.tool || 'tool call'

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        'rounded-md border bg-muted/30 transition-colors',
        ok ? 'border-border/60' : 'border-red-500/40 border-l-2 border-l-red-500/60',
      )}
    >
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-muted/50">
        <span className="flex size-4 shrink-0 items-center justify-center">
          {ok ? (
            <CheckIcon className="size-3.5 text-green-600 dark:text-green-500" />
          ) : (
            <XCircleIcon className="size-3.5 text-red-600 dark:text-red-500" />
          )}
        </span>
        <span className="shrink-0 font-mono text-[11px] text-foreground/80">{fields.tool}</span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">{label}</span>
        {fields.durationMs != null ? (
          <span className="flex shrink-0 items-center gap-1 tabular-nums text-muted-foreground/70">
            <ClockIcon className="size-3" />
            {fields.durationMs}ms
          </span>
        ) : null}
        <ChevronDownIcon className={cn('size-3 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-2 border-t border-border/50 px-2.5 py-2 text-xs">
          {fields.argsSummary ? (
            <SummaryList title="Args" entries={fields.argsSummary} />
          ) : null}
          {fields.resultSummary ? (
            <SummaryList title="Result" entries={fields.resultSummary} />
          ) : null}
          {fields.error ? (
            <p className="font-medium text-red-600 dark:text-red-400">{fields.error}</p>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function SummaryList({
  title,
  entries,
}: {
  title: string
  entries: Record<string, JsonValue>
}) {
  const keys = Object.keys(entries)
  if (keys.length === 0) return null
  return (
    <div>
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
        {title}
      </p>
      <dl className="flex flex-col gap-0.5 font-mono text-[11px] text-muted-foreground">
        {keys.map((key) => (
          <div key={key} className="flex gap-2">
            <dt className="shrink-0 text-muted-foreground/60">{key}:</dt>
            <dd className="break-all text-foreground/80">{formatJsonValue(entries[key])}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function QuestionEvent({
  event,
  runStatus,
  onSend,
}: {
  event: RunEvent
  runStatus: string
  onSend?: (text: string) => void | Promise<void>
}) {
  const payload = eventPayload(event)
  const choices = stringArray(payload.choices)
  const context = stringValue(payload.context)
  const [picked, setPicked] = useState<string | null>(null)
  const answerable = runStatus === 'needs_user' && onSend

  const handlePick = (choice: string) => {
    if (!answerable || picked) return
    setPicked(choice)
    void onSend(choice)
  }

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
              {choices.map((choice) => {
                const isPicked = picked === choice
                const disabled = !answerable || (picked !== null && !isPicked)
                return (
                  <button
                    key={choice}
                    type="button"
                    disabled={disabled}
                    onClick={() => handlePick(choice)}
                    className={cn(
                      'max-w-full whitespace-normal rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                      isPicked
                        ? 'border-primary bg-primary text-primary-foreground'
                        : answerable
                          ? 'border-border bg-secondary text-secondary-foreground hover:bg-secondary/80'
                          : 'border-border bg-secondary/50 text-muted-foreground',
                      answerable && !isPicked && 'cursor-pointer',
                      disabled && 'cursor-not-allowed opacity-70',
                    )}
                  >
                    {choice}
                  </button>
                )
              })}
            </div>
          ) : null}
          {!answerable && choices.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Reply below to answer the agent.
            </p>
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
    <RunTerminalMessage
      status={status}
      title={event.title || 'Run result'}
      markdown={event.markdown}
    />
  )
}

function TerminalStatus({ run }: { run: Run }) {
  // A failed run with no result and a failed/zero trigger usually means the
  // trigger HTTP call never got a 202 — but the ChatGPT agent may still have
  // been dispatched and tried to write back, only to be rejected because this
  // run is already terminal. Surface that distinctly instead of misleadingly
  // saying the agent "finished without a result".
  const triggerFailed =
    run.status === 'failed' &&
    (run.trigger_status === 'failed' || run.trigger_http_status === 0)
  if (triggerFailed) {
    return (
      <RunTerminalMessage
        status={run.status}
        title="Trigger failed"
        description="The relay could not confirm the trigger reached ChatGPT. The agent may still be running, but its updates were rejected because this run was marked failed. Try sending the message again."
      />
    )
  }
  return (
    <RunTerminalMessage
      status={run.status}
      title="Run finished"
      description="Run finished without a result event."
    />
  )
}

function RunTerminalMessage({
  status,
  title,
  markdown,
  description,
}: {
  status: string
  title: string
  markdown?: string
  description?: string
}) {
  return (
    <Message from="assistant">
      <MessageContent>
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={status} />
            <span className="text-xs font-medium text-muted-foreground">{title}</span>
          </div>
          {markdown ? <MessageResponse>{markdown}</MessageResponse> : null}
          {!markdown && description ? (
            <p className="text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
      </MessageContent>
    </Message>
  )
}

function ThreadLoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6 py-4" aria-label="Loading conversation">
      <div className="ml-auto flex w-4/5 flex-col items-end gap-2">
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-16 w-full rounded-lg" />
      </div>
      <div className="flex w-5/6 flex-col gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  )
}

function phaseHint(detail: RunDetail): string | null {
  const run = detail.run
  if (detail.events.length > 0 || detail.plan) return null
  if (run.status === 'trigger_failed' || run.trigger_status === 'failed' || run.status === 'failed') {
    return 'Trigger failed. The agent may still be running — waiting for a callback to confirm.'
  }
  if (run.trigger_status === 'accepted') {
    return 'Trigger accepted (202). Waiting for the agent to call back via MCP.'
  }
  return `Trigger ${run.trigger_status || run.status || 'pending'}. Waiting for callback events.`
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

function isTraceEvent(event: RunEvent): boolean {
  return eventPayload(event).trace === true
}

function traceFields(event: RunEvent): ToolTraceFields {
  const payload = eventPayload(event)
  return {
    tool: stringValue(payload.tool) || (event.title ? deriveToolFromTitle(event.title) : 'tool'),
    title: stringValue(payload.title) || event.title || '',
    argsSummary: objectValue(payload.args_summary),
    resultSummary: objectValue(payload.result_summary),
    startedAt: stringValue(payload.started_at),
    durationMs: numberValue(payload.duration_ms),
    ok: payload.ok !== false,
    error: stringValue(payload.error) || null,
  }
}

function objectValue(value: JsonValue | undefined): Record<string, JsonValue> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, JsonValue>
  }
  return null
}

function numberValue(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function deriveToolFromTitle(title: string): string {
  // Titles look like "apply_patch → ThreadView.tsx"; take the leading token.
  return title.split(/[\s→]/, 1)[0] || 'tool'
}

function formatJsonValue(value: JsonValue): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}
