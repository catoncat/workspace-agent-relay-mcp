import type { Agent, Conversation, Run, RunDetail, RunEventPayload, TokenRef } from './types'

// This dashboard is a local/admin surface. localStorage keeps setup simple, but it is not
// XSS-hardened like an httpOnly cookie, so the API token should stay scoped to this relay.
const TOKEN_KEY = 'relayAuthToken'

function devAuthTokenFromEnv(): string {
  if (!import.meta.env.DEV) return ''
  return import.meta.env.VITE_RELAY_AUTH_TOKEN?.trim() ?? ''
}

export function getAuthToken(): string {
  const stored = localStorage.getItem(TOKEN_KEY)?.trim()
  if (stored) return stored
  return devAuthTokenFromEnv()
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token.trim())
}

function headers(): HeadersInit {
  const token = getAuthToken()
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) h.Authorization = `Bearer ${token}`
  return h
}

function formatApiError(text: string): string {
  try {
    const body = JSON.parse(text) as { error?: string; detail?: string }
    const message = body.error?.trim() || body.detail?.trim()
    if (!message) return text || 'Request failed'
    if (message.includes('access token') || message.includes('WORKSPACE_AGENT_RELAY_AGENT_TOKEN')) {
      return (
        'Workspace Agent access token is missing for this agent. ' +
        'Open Settings, select the agent, and paste its access token from ChatGPT.'
      )
    }
    return message
  } catch {
    return text || 'Request failed'
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { ...headers(), ...(init?.headers as Record<string, string> | undefined) },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(formatApiError(text))
  }
  return response.json() as Promise<T>
}

export async function listAgents(): Promise<Agent[]> {
  return api('/api/agents')
}

export async function ensureDefaultAgent(): Promise<Agent[]> {
  return listAgents()
}

// Legacy: env-backed token refs for deployments that still use .env tokens.
export async function listTokenRefs(): Promise<TokenRef[]> {
  return api('/api/agents/token-refs')
}

export async function createAgent(body: {
  name: string
  trigger_url: string
  access_token: string
}): Promise<Agent> {
  return api('/api/agents', { method: 'POST', body: JSON.stringify(body) })
}

export async function updateAgent(
  agentId: number,
  body: { name?: string; access_token?: string },
): Promise<Agent> {
  return api(`/api/agents/${agentId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function renameAgent(agentId: number, name: string): Promise<Agent> {
  return updateAgent(agentId, { name })
}

export async function deleteAgent(agentId: number): Promise<{ success: boolean }> {
  return api(`/api/agents/${agentId}`, { method: 'DELETE' })
}

export async function listConversations(): Promise<Conversation[]> {
  return api('/api/conversations')
}

export async function createConversation(body: {
  agent_id: number
  name: string
  conversation_key: string
}): Promise<Conversation> {
  return api('/api/conversations', { method: 'POST', body: JSON.stringify(body) })
}

export async function updateConversation(
  conversationId: number,
  body: { name?: string; pinned?: boolean },
): Promise<Conversation> {
  return api(`/api/conversations/${conversationId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function renameConversation(
  conversationId: number,
  name: string,
): Promise<Conversation> {
  return updateConversation(conversationId, { name })
}

export async function setConversationPinned(
  conversationId: number,
  pinned: boolean,
): Promise<Conversation> {
  return updateConversation(conversationId, { pinned })
}

export async function deleteConversation(conversationId: number): Promise<{ success: boolean }> {
  return api(`/api/conversations/${conversationId}`, { method: 'DELETE' })
}

export async function ensureDefaultConversation(agentId: number): Promise<Conversation[]> {
  let conversations = await listConversations()
  if (conversations.length === 0) {
    const key = `default:${new Date().toISOString().slice(0, 10)}`
    await createConversation({ agent_id: agentId, name: 'Default', conversation_key: key })
    conversations = await listConversations()
  }
  return conversations
}

export async function listRuns(conversationId: number): Promise<Run[]> {
  return api(`/api/conversations/${conversationId}/runs`)
}

export async function getRunDetail(runId: number): Promise<RunDetail> {
  return normalizeRunDetail(await api(`/api/runs/${runId}`))
}

export async function dismissRun(runId: number, note?: string): Promise<RunDetail> {
  return normalizeRunDetail(
    await api(`/api/runs/${runId}/dismiss`, {
      method: 'POST',
      body: JSON.stringify(note ? { note } : {}),
    }),
  )
}

export type CreateRunResponse = {
  run: Run
  triggerFailed: boolean
  warning?: string
}

export async function createRun(
  conversationId: number,
  input_markdown: string,
): Promise<CreateRunResponse> {
  const response = await fetch(`/api/conversations/${conversationId}/runs`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ input_markdown }),
  })
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }

  if (response.ok && body && typeof body === 'object' && 'id' in body) {
    return { run: body as Run, triggerFailed: false }
  }

  if (
    response.status === 502 &&
    body &&
    typeof body === 'object' &&
    'run' in body &&
    body.run &&
    typeof body.run === 'object' &&
    'id' in body.run
  ) {
    const payload = body as { error?: string; run: Run }
    return {
      run: payload.run,
      triggerFailed: true,
      warning: payload.error?.trim() || 'Trigger request failed',
    }
  }

  throw new Error(formatApiError(text))
}

// Append guidance to the active run in this conversation (steer): same run,
// rotated callback_token, same request_id. The backend returns the updated
// run on success / 502 (trigger failed but run updated). On 409 there is no
// active run to steer (race: it went terminal between SSE status and send),
// so fall back to creating a new turn. The response shape matches createRun
// so callers can treat both uniformly.
export async function steerConversation(
  conversationId: number,
  input_markdown: string,
): Promise<CreateRunResponse> {
  const response = await fetch(`/api/conversations/${conversationId}/steer`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ input_markdown }),
  })
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }

  if (response.status === 409) {
    return createRun(conversationId, input_markdown)
  }

  if (response.ok && body && typeof body === 'object' && 'id' in body) {
    return { run: body as Run, triggerFailed: false }
  }

  if (
    response.status === 502 &&
    body &&
    typeof body === 'object' &&
    'run' in body &&
    body.run &&
    typeof body.run === 'object' &&
    'id' in body.run
  ) {
    const payload = body as { error?: string; run: Run }
    return {
      run: payload.run,
      triggerFailed: true,
      warning: payload.error?.trim() || 'Trigger request failed',
    }
  }

  throw new Error(formatApiError(text))
}

export function streamRun(
  runId: number,
  onDetail: (detail: RunDetail) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getAuthToken()
  const streamHeaders: Record<string, string> = { Accept: 'text/event-stream' }
  if (token) streamHeaders.Authorization = `Bearer ${token}`

  return (async () => {
    const response = await fetch(`/api/runs/${runId}/stream`, { headers: streamHeaders, signal })
    if (!response.ok || !response.body) {
      throw new Error(formatApiError(await response.text()))
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        if (buffer.trim()) emitSseMessage(buffer, onDetail)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split(/\r?\n\r?\n/)
      buffer = parts.pop() || ''
      for (const part of parts) {
        emitSseMessage(part, onDetail)
      }
    }
  })()
}

function emitSseMessage(raw: string, onDetail: (detail: RunDetail) => void): void {
  const data = raw
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace(/^data:\s?/, ''))
    .join('\n')

  if (!data) return
  try {
    onDetail(normalizeRunDetail(JSON.parse(data) as RunDetail))
  } catch {
    /* ignore malformed SSE data frames */
  }
}

function normalizeRunDetail(detail: RunDetail): RunDetail {
  return {
    ...detail,
    events: detail.events.map((event) => ({
      ...event,
      payload: event.payload ?? parsePayloadJson(event.payload_json),
    })),
  }
}

function parsePayloadJson(value: string | undefined): RunEventPayload {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as RunEventPayload
    }
  } catch {
    return {}
  }
  return {}
}
