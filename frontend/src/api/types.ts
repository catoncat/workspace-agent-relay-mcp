export type Agent = {
  id: number
  name: string
  trigger_url: string
  trigger_id: string
  token_ref: string
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

export type RunDetail = {
  run: Run
  events: RunEvent[]
  artifacts: Artifact[]
}
