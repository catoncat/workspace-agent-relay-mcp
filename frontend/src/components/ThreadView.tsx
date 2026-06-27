import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
import {
  Message,
  MessageContent,
} from '@/components/ai-elements/message'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { ThreadProse } from '@/components/ThreadProse'
import { cn } from '@/lib/utils'
import {
  RUN_ACTIVE_STATUSES,
  RUN_TERMINAL_STATUSES,
} from '@/lib/runStatus'
import type { JsonValue, Plan, PlanStep, PlanStepStatus, Run, RunDetail, RunEvent, RunEventPayload, ToolTraceFields } from '@/api/types'
import {
  CheckIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CircleIcon,
  LoaderCircleIcon,
  MinusIcon,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

const ACTIVE_STATUSES = RUN_ACTIVE_STATUSES
const TERMINAL_STATUSES = RUN_TERMINAL_STATUSES

type TimelineSegment =
  | { kind: 'traces'; events: RunEvent[] }
  | { kind: 'narration'; event: RunEvent }

/** Split progress events at narration boundaries so tool batches and notes
 * render in causal order instead of two fixed buckets. */
export function buildTimelineSegments(events: RunEvent[]): TimelineSegment[] {
  const segments: TimelineSegment[] = []
  let traceBatch: RunEvent[] = []

  for (const event of events) {
    if (isTraceEvent(event)) {
      traceBatch.push(event)
      continue
    }
    if (traceBatch.length > 0) {
      segments.push({ kind: 'traces', events: traceBatch })
      traceBatch = []
    }
    segments.push({ kind: 'narration', event })
  }

  if (traceBatch.length > 0) {
    segments.push({ kind: 'traces', events: traceBatch })
  }

  return segments
}

type Props = {
  details: RunDetail[]
  loading?: boolean
  onSend?: (text: string) => void | Promise<void>
}

export function ThreadView({ details, loading = false, onSend }: Props) {
  const activeDetail = useMemo(() => pickActiveRunDetail(details), [details])

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
      {activeDetail ? (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 bg-gradient-to-b from-background from-60% via-background/90 to-transparent px-4 pb-6 pt-4">
          <div className="mx-auto max-w-3xl">
            <StickyPlanBar detail={activeDetail} />
          </div>
        </div>
      ) : null}
      <ConversationContent className="mx-auto max-w-3xl gap-6">
        {details.map((detail, index) => (
          <RunThread
            key={detail.run.id}
            detail={detail}
            onSend={onSend}
            authoritativeRunId={activeDetail?.run.id ?? null}
            turnIndex={index + 1}
          />
        ))}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

function RunThread({
  detail,
  onSend,
  authoritativeRunId,
  turnIndex,
}: {
  detail: RunDetail
  onSend?: (text: string) => void | Promise<void>
  authoritativeRunId: number | null
  turnIndex: number
}) {
  const run = detail.run
  const isActive = ACTIVE_STATUSES.has(run.status)
  const isAuthoritative = authoritativeRunId === run.id
  const planSuperseded =
    run.status === 'superseded' ||
    Boolean(isActive && detail.plan && authoritativeRunId != null && !isAuthoritative)
  const planEventCount = detail.events.filter((event) => event.event_type === 'plan').length
  const planRevised = planEventCount >= 2
  const planActive = isActive && isAuthoritative
  const hasResultEvent = detail.events.some((event) => event.event_type === 'result')
  const progressEvents = detail.events.filter(
    (event) => event.event_type === 'progress' && (event.markdown || event.title),
  )
  const systemEvents = detail.events.filter(
    (event) => event.event_type === 'system' && (event.markdown || event.title),
  )
  const hasSystemEvent = systemEvents.length > 0

  return (
    <div id={`run-${run.id}`} className="flex flex-col gap-3 scroll-mt-16 pl-0.5">
      <div className="flex items-center gap-2 px-1 text-[11px] font-medium text-muted-foreground/70">
        <span className="tabular-nums">Turn {turnIndex}</span>
        {run.status !== 'done' ? <StatusBadge status={run.status} /> : null}
      </div>

      <Message from="user">
        <MessageContent>
          <ThreadProse>{run.input_markdown || '(empty message)'}</ThreadProse>
        </MessageContent>
      </Message>

      {detail.plan && !planActive ? (
        <PlanCompactLine
          plan={detail.plan}
          superseded={planSuperseded}
          revised={planRevised}
        />
      ) : null}

      <RunPhaseHint detail={detail} />

      {progressEvents.length > 0 ? (
        <RunProgressTimeline
          events={progressEvents}
          isActive={isActive}
          hasResultEvent={hasResultEvent}
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

      {systemEvents.map((event, index) => (
        <SystemEvent
          key={`system-${event.id ?? index}`}
          event={event}
          runStatus={run.status}
        />
      ))}

      {!hasResultEvent && !hasSystemEvent && TERMINAL_STATUSES.has(run.status) ? (
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

function PlanCompactLine({
  plan,
  superseded = false,
  revised = false,
}: {
  plan: Plan
  superseded?: boolean
  revised?: boolean
}) {
  const { doneCount, total } = planProgress(plan)
  const tags = [
    superseded ? 'superseded' : null,
    revised ? 'revised' : null,
  ].filter(Boolean)

  return (
    <p className="px-1 text-xs text-muted-foreground">
      Plan {doneCount}/{total}
      {tags.length > 0 ? ` · ${tags.join(' · ')}` : null}
    </p>
  )
}

function StickyPlanBar({ detail }: { detail: RunDetail }) {
  const [expanded, setExpanded] = useState(true)
  const plan = detail.plan
  if (!plan) return null
  const { doneCount, total, currentStep } = planProgress(plan)
  const isLive = ACTIVE_STATUSES.has(detail.run.status)

  return (
    <div className="pointer-events-auto w-full overflow-hidden rounded-xl border border-border/70 bg-background/95 shadow-md backdrop-blur-md">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="group w-full p-3 text-left transition-colors hover:bg-muted/30"
        aria-expanded={expanded}
      >
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <span>Plan</span>
          <span className="tabular-nums text-foreground">
            {doneCount}/{total}
          </span>
          <span className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground/80 transition-colors group-hover:text-muted-foreground">
            <span className="hidden sm:inline">{expanded ? 'Collapse' : 'Expand'}</span>
            {expanded ? (
              <ChevronUpIcon className="size-3.5 shrink-0" />
            ) : (
              <ChevronDownIcon className="size-3.5 shrink-0" />
            )}
          </span>
        </div>

        {!expanded ? (
          <p className="truncate text-sm leading-snug text-foreground">
            {currentStep ? currentStep.title : 'Working…'}
          </p>
        ) : null}

        <div className={cn('flex items-center gap-1', expanded ? 'mt-0' : 'mt-2.5')} aria-hidden="true">
          {plan.steps.map((step) => (
            <span
              key={step.id}
              className={cn(
                'h-1 min-w-0 flex-1 rounded-full transition-colors',
                step.status === 'done' && 'bg-primary/70',
                step.status === 'in_progress' && 'bg-primary',
                step.status === 'skipped' && 'bg-muted-foreground/25',
                step.status === 'pending' && 'bg-muted',
              )}
            />
          ))}
        </div>
      </button>

      {expanded ? (
        <div className="border-t border-border/60 px-3 pb-3 pt-2">
          <ol className="space-y-1.5">
            {plan.steps.map((step, index) => (
              <PlanStepRow
                key={step.id}
                step={step}
                live={isLive}
                delayMs={index * 80}
              />
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}

function PlanStepRow({ step, live, delayMs }: { step: PlanStep; live: boolean; delayMs: number }) {
  const displayStatus = !live && step.status === 'in_progress' ? 'pending' : step.status
  const { icon, className } = stepVisual(displayStatus)
  return (
    <li className="flex items-start gap-2.5 text-sm">
      <span
        className={cn('mt-0.5 flex size-4 shrink-0 items-center justify-center transition-all', className)}
        style={live ? { transitionDelay: `${delayMs}ms` } : undefined}
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <span
          className={cn(
            'transition-colors',
            displayStatus === 'done' && 'text-muted-foreground line-through decoration-muted-foreground/40',
            displayStatus === 'skipped' && 'text-muted-foreground/60 line-through',
            displayStatus === 'pending' && 'text-foreground/80',
            displayStatus === 'in_progress' && 'text-foreground',
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
    <div className="text-sm text-muted-foreground">
      {isActive ? (
        <Shimmer className="text-sm" duration={1.5}>
          {hint}
        </Shimmer>
      ) : (
        <p className="whitespace-pre-line">{hint}</p>
      )}
    </div>
  )
}

function RunProgressTimeline({
  events,
  isActive,
  hasResultEvent,
}: {
  events: RunEvent[]
  isActive: boolean
  hasResultEvent: boolean
}) {
  const segments = useMemo(() => buildTimelineSegments(events), [events])
  const lastNarrationIndex = useMemo(() => {
    for (let index = segments.length - 1; index >= 0; index -= 1) {
      if (segments[index]?.kind === 'narration') return index
    }
    return -1
  }, [segments])
  const lastTraceSegmentIndex = useMemo(() => {
    for (let index = segments.length - 1; index >= 0; index -= 1) {
      if (segments[index]?.kind === 'traces') return index
    }
    return -1
  }, [segments])

  return (
    <div className="flex flex-col gap-4">
      {segments.map((segment, index) => {
        if (segment.kind === 'narration') {
          const live = isActive && !hasResultEvent && index === lastNarrationIndex
          return (
            <NarrationItem
              key={`narr-${segment.event.id ?? index}`}
              event={segment.event}
              live={live}
            />
          )
        }

        const isLiveBatch = isActive && !hasResultEvent && index === lastTraceSegmentIndex
        return (
          <ToolTraceBatch
            key={`traces-${segment.events[0]?.id ?? index}`}
            events={segment.events}
            defaultExpanded={isLiveBatch}
          />
        )
      })}
    </div>
  )
}

function NarrationItem({ event, live = false }: { event: RunEvent; live?: boolean }) {
  const titleDuplicatesMarkdown =
    !!event.title && !!event.markdown && event.title.trim() === event.markdown.trim()
  return (
    <div className="space-y-1">
      {event.title && !titleDuplicatesMarkdown ? (
        <p className="text-sm font-medium text-foreground">{event.title}</p>
      ) : null}
      {event.markdown ? (
        <ThreadProse
          live={live}
          className={event.title && !titleDuplicatesMarkdown ? 'mt-1' : undefined}
        >
          {event.markdown}
        </ThreadProse>
      ) : null}
    </div>
  )
}

function ToolTraceBatch({
  events,
  defaultExpanded,
}: {
  events: RunEvent[]
  defaultExpanded: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  useEffect(() => {
    if (defaultExpanded) setExpanded(true)
  }, [defaultExpanded])

  if (!expanded && events.length > 1) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronDownIcon className="size-3.5 shrink-0" />
        <span>{events.length} tool calls</span>
      </button>
    )
  }

  return (
    <ul className="my-1 list-none space-y-1 pl-0 text-sm text-muted-foreground">
      {events.map((event, index) => (
        <ToolTraceListItem key={`trace-${event.id ?? index}`} event={event} />
      ))}
    </ul>
  )
}

function ToolTraceListItem({ event }: { event: RunEvent }) {
  const [showDetails, setShowDetails] = useState(false)
  const fields = traceFields(event)
  const hasDetails = Boolean(fields.argsSummary || fields.resultSummary || fields.error)
  const label = formatToolCallLabel(fields)

  return (
    <li className={cn('flex gap-2.5 py-0.5', !fields.ok && 'text-destructive')}>
      <span
        aria-hidden
        className={cn(
          'mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/45',
          !fields.ok && 'bg-destructive/60',
        )}
      />
      <span className="min-w-0 flex-1">
        <button
          type="button"
          disabled={!hasDetails}
          onClick={() => setShowDetails((value) => !value)}
          className={cn(
            'text-left transition-colors',
            hasDetails && 'cursor-pointer hover:text-foreground',
            !hasDetails && 'cursor-default',
          )}
        >
          {label}
          {!fields.ok ? ' · failed' : null}
        </button>
        {showDetails && hasDetails ? (
          <div className="mt-1 space-y-1.5 text-xs text-muted-foreground">
            {fields.argsSummary ? (
              <SummaryList title="Args" entries={fields.argsSummary} />
            ) : null}
            {fields.resultSummary ? (
              <SummaryList title="Result" entries={fields.resultSummary} />
            ) : null}
            {fields.error ? (
              <p className="text-destructive">{fields.error}</p>
            ) : null}
          </div>
        ) : null}
      </span>
    </li>
  )
}

function formatToolCallLabel(fields: ToolTraceFields): string {
  if (fields.title.trim()) return fields.title
  const tool = fields.tool.replace(/_/g, ' ')
  return `Calling ${tool}`
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
      <p className="mb-1 text-[11px] text-muted-foreground/80">{title}</p>
      <dl className="flex flex-col gap-0.5 text-[11px]">
        {keys.map((key) => (
          <div key={key} className="flex gap-2">
            <dt className="shrink-0 text-muted-foreground/70">{key}</dt>
            <dd className="min-w-0 break-all text-foreground/80">{formatJsonValue(entries[key])}</dd>
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
    <div className="space-y-3">
      <p className="text-xs font-medium text-muted-foreground">
        {event.title || 'User input needed'}
      </p>
      {event.markdown ? <ThreadProse>{event.markdown}</ThreadProse> : null}
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

function SystemEvent({ event, runStatus }: { event: RunEvent; runStatus: string }) {
  return (
    <RunTerminalMessage
      status={runStatus}
      title={event.title || 'System update'}
      markdown={event.markdown}
    />
  )
}

function TerminalStatus({ run }: { run: Run }) {
  if (run.status === 'superseded') {
    return (
      <RunTerminalMessage
        status={run.status}
        title="Superseded by newer turn"
        description="A newer turn was sent before this one produced a final callback, so late updates from this run are ignored."
      />
    )
  }

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
      title="Closed without final callback"
      description="No record_result callback was received for this run. In this relay UI that usually means the turn was manually closed or interrupted before the agent sent a final result."
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
  const isFailed = status === 'failed' || status === 'trigger_failed' || status === 'blocked'
  const titleDuplicatesMarkdown =
    !!markdown && !!title && title.trim() === markdown.trim()
  return (
    <div className="space-y-1.5">
      {title && !titleDuplicatesMarkdown ? (
        <p
          className={cn(
            'text-xs font-medium',
            isFailed ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {title}
        </p>
      ) : null}
      {markdown ? <ThreadProse>{markdown}</ThreadProse> : null}
      {!markdown && description ? (
        <p className="text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
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
  if (run.status === 'draft' || run.trigger_status === 'draft') {
    return 'Sending trigger to ChatGPT. Callback events can appear only after the Workspace Agent starts.'
  }
  if (run.status === 'trigger_failed' || run.trigger_status === 'failed' || run.status === 'failed') {
    const reason = run.trigger_error?.trim()
    const base = 'Trigger did not return a clean 202. This run stays open for late callbacks, but sending a newer turn will supersede it.'
    return reason ? `${base}\n${reason}` : base
  }
  if (run.trigger_status === 'accepted') {
    return 'Trigger accepted by ChatGPT. Waiting for the agent to call back through this relay MCP.'
  }
  return `Trigger state: ${run.trigger_status || run.status || 'pending'}. Waiting for callback events.`
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
