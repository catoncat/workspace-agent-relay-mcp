export type Agent = {
  id: number
  name: string
  trigger_url: string
  trigger_id: string
  token_ref: string
}

// A token_ref the relay knows how to resolve (from its config snapshot). The
// "create agent" form lists these in a dropdown so the user never types a raw
// env var name. Only the ref/env var name is exposed — never the token value.
export type TokenRef = {
  token_ref: string
  env_var: string
  is_default: boolean
}

export type Conversation = {
  id: number
  agent_id: number
  name: string
  conversation_key: string
}

export type Run = {
  id: number
  request_id: string
  status: string
  conversation_key: string
  input_markdown: string
  trigger_status?: string
  trigger_http_status?: number
  trigger_x_request_id?: string
  trigger_error?: string | null
  conversation_url?: string
  idempotency_key?: string
  created_at?: string
  completed_at?: string
}

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

export type RunEventPayload = Record<string, JsonValue>

// Loose, JsonValue-based shape for tool-call trace payloads mirrored from
// notion-local-ops. The summaries are arbitrary dicts, so keep this permissive.
export type ToolTraceFields = {
  tool: string
  title: string
  argsSummary: Record<string, JsonValue> | null
  resultSummary: Record<string, JsonValue> | null
  startedAt: string
  durationMs: number | null
  ok: boolean
  error: string | null
}

export type RunEvent = {
  id?: number
  event_type: string
  title?: string
  markdown?: string
  payload?: RunEventPayload
  payload_json?: string
  created_at?: string
}

export type Artifact = {
  name: string
  mime_type: string
  content: string
}

export type PlanStepStatus = 'pending' | 'in_progress' | 'done' | 'skipped'

export type PlanStep = {
  id: string
  title: string
  status: PlanStepStatus
  note?: string
}

export type Plan = {
  run_id: number
  steps: PlanStep[]
  created_at?: string
  updated_at?: string
}

export type RunDetail = {
  run: Run
  events: RunEvent[]
  artifacts: Artifact[]
  plan?: Plan | null
}
