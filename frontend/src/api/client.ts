import type { Agent, Conversation, Run, RunDetail, RunEventPayload } from './types'

// This dashboard is a local/admin surface. localStorage keeps setup simple, but it is not
// XSS-hardened like an httpOnly cookie, so the API token should stay scoped to this relay.
const TOKEN_KEY = 'relayAuthToken'

export function getAuthToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
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
    const body = JSON.parse(text) as { error?: string }
    const message = body.error?.trim()
    if (!message) return text || 'Request failed'
    if (message.includes('WORKSPACE_AGENT_RELAY_AGENT_TOKEN')) {
      return (
        'Workspace Agent token is missing on the relay server. ' +
        'Set WORKSPACE_AGENT_RELAY_AGENT_TOKEN in .env (server-side; not the dashboard API token), ' +
        'then restart workspace-agent-relay-mcp.'
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
  let agents = await listAgents()
  if (agents.length === 0) {
    await api('/api/agents', {
      method: 'POST',
      body: JSON.stringify({
        name: 'default',
        trigger_url: '',
        token_ref: 'env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN',
      }),
    })
    agents = await listAgents()
  }
  return agents
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

export async function renameConversation(
  conversationId: number,
  name: string,
): Promise<Conversation> {
  return api(`/api/conversations/${conversationId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
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
