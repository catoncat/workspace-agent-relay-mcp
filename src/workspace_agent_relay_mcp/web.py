from __future__ import annotations

from contextlib import asynccontextmanager
import json
import sqlite3
from typing import Any, Callable
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from .http_compat import HTTPBearerAuthMiddleware, build_http_compat_app
from .oauth import OAuthManager
from .trigger import TriggerClient, build_trigger_input, generate_callback_token, generate_request_id


SUPPORTED_AGENT_TOKEN_REF = "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN"
WORKSPACE_AGENT_TRIGGER_HOST = "api.chatgpt.com"
WORKSPACE_AGENT_TRIGGER_PREFIX = "/v1/workspace_agents/"
WORKSPACE_AGENT_TRIGGER_SUFFIX = "/trigger"


class APIBearerAuthMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        get_auth_token: Callable[[], str],
        get_oauth_config: Callable[[], Any],
        get_oauth_manager: Callable[[], OAuthManager],
    ) -> None:
        self.app = app
        self._api_auth_app = HTTPBearerAuthMiddleware(
            app,
            get_auth_token=get_auth_token,
            get_oauth_config=get_oauth_config,
            get_oauth_manager=get_oauth_manager,
            mcp_path="/mcp",
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and str(scope.get("path", "")).startswith("/api/"):
            await self._api_auth_app(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _json_error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": message}, status_code=status_code)


async def _json(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed JSON body") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _validate_trigger_url(trigger_url: str) -> None:
    parsed = urlparse(trigger_url)
    trigger_id = ""
    if parsed.path.startswith(WORKSPACE_AGENT_TRIGGER_PREFIX) and parsed.path.endswith(WORKSPACE_AGENT_TRIGGER_SUFFIX):
        trigger_id = parsed.path[len(WORKSPACE_AGENT_TRIGGER_PREFIX) : -len(WORKSPACE_AGENT_TRIGGER_SUFFIX)]
    if (
        parsed.scheme != "https"
        or parsed.netloc != WORKSPACE_AGENT_TRIGGER_HOST
        or not trigger_id
        or "/" in trigger_id
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("trigger_url must be a ChatGPT Workspace Agent trigger endpoint")


def _validate_agent_token_ref(token_ref: str) -> None:
    if token_ref != SUPPORTED_AGENT_TOKEN_REF:
        raise ValueError(f"unsupported token_ref: {token_ref}")


def _agent_token(config: Any, token_ref: str) -> str:
    _validate_agent_token_ref(token_ref)
    token = str(config.default_agent_token)
    if not token:
        raise ValueError("WORKSPACE_AGENT_RELAY_AGENT_TOKEN is not configured")
    return token


def _missing_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if payload.get(field) in (None, "")]


def _dashboard_html() -> str:
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Workspace Agent Relay</title>
    <style>
      :root {
        color-scheme: light;
        --background: #fafafa;
        --foreground: #18181b;
        --muted: #71717a;
        --muted-2: #a1a1aa;
        --panel: #ffffff;
        --panel-subtle: #f4f4f5;
        --border: #e4e4e7;
        --border-strong: #d4d4d8;
        --primary: #18181b;
        --primary-foreground: #ffffff;
        --accent: #2563eb;
        --accent-soft: #eff6ff;
        --success: #15803d;
        --success-soft: #f0fdf4;
        --warning: #a16207;
        --warning-soft: #fefce8;
        --danger: #b91c1c;
        --danger-soft: #fef2f2;
        --shadow: 0 1px 2px rgba(24, 24, 27, 0.06);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font: 14px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--foreground);
        background: var(--background);
      }
      button, input, textarea {
        font: inherit;
      }
      button {
        border: 1px solid var(--border);
        border-radius: 8px;
        min-height: 34px;
        padding: 7px 10px;
        color: var(--foreground);
        background: var(--panel);
        cursor: pointer;
      }
      button:hover {
        background: var(--panel-subtle);
      }
      button.primary {
        border-color: var(--primary);
        background: var(--primary);
        color: var(--primary-foreground);
      }
      button.ghost {
        border-color: transparent;
        background: transparent;
      }
      input, textarea {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 8px;
        color: var(--foreground);
        background: var(--panel);
        outline: none;
      }
      input:focus, textarea:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px var(--accent-soft);
      }
      input {
        min-height: 36px;
        padding: 8px 10px;
      }
      textarea {
        min-height: 96px;
        resize: vertical;
        padding: 11px 12px;
      }
      .app {
        display: grid;
        grid-template-columns: 292px minmax(420px, 1fr) 360px;
        min-height: 100vh;
      }
      .sidebar, .thread, .inspector {
        min-width: 0;
        background: var(--panel);
      }
      .sidebar {
        border-right: 1px solid var(--border);
        display: flex;
        flex-direction: column;
      }
      .thread {
        display: grid;
        grid-template-rows: auto 1fr auto;
        background: var(--background);
      }
      .inspector {
        border-left: 1px solid var(--border);
        display: flex;
        flex-direction: column;
      }
      .side-header, .thread-header, .inspector-header {
        padding: 14px 16px;
        border-bottom: 1px solid var(--border);
      }
      .side-scroll, .messages, .inspector-scroll {
        min-height: 0;
        overflow: auto;
      }
      .side-scroll, .inspector-scroll {
        padding: 14px;
      }
      h1 {
        margin: 0;
        font-size: 15px;
        line-height: 1.2;
        font-weight: 650;
      }
      h2 {
        margin: 18px 0 8px;
        color: var(--muted);
        font-size: 11px;
        line-height: 1.2;
        font-weight: 650;
        letter-spacing: 0.03em;
        text-transform: uppercase;
      }
      label {
        display: block;
        margin: 0 0 6px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 500;
      }
      .subtle {
        color: var(--muted);
      }
      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        overflow-wrap: anywhere;
      }
      .row {
        display: flex;
        gap: 8px;
        align-items: center;
      }
      .row.between {
        justify-content: space-between;
      }
      .stack {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .token-box {
        padding: 10px;
        border: 1px solid var(--border);
        border-radius: 10px;
        background: var(--panel-subtle);
      }
      .item {
        width: 100%;
        display: block;
        margin: 0 0 8px;
        text-align: left;
        border-radius: 10px;
        background: var(--panel);
        box-shadow: var(--shadow);
      }
      .item[aria-selected="true"] {
        border-color: var(--accent);
        background: var(--accent-soft);
      }
      .item-title {
        display: block;
        font-weight: 600;
      }
      .item-meta {
        display: block;
        margin-top: 4px;
        color: var(--muted);
        font-size: 12px;
      }
      .badge {
        display: inline-flex;
        align-items: center;
        min-height: 22px;
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 2px 8px;
        color: var(--muted);
        background: var(--panel);
        font-size: 12px;
        font-weight: 500;
      }
      .badge.accepted, .badge.waiting {
        border-color: #fde68a;
        color: var(--warning);
        background: var(--warning-soft);
      }
      .badge.done {
        border-color: #bbf7d0;
        color: var(--success);
        background: var(--success-soft);
      }
      .badge.failed, .badge.blocked {
        border-color: #fecaca;
        color: var(--danger);
        background: var(--danger-soft);
      }
      .badge.needs_user {
        border-color: #bfdbfe;
        color: var(--accent);
        background: var(--accent-soft);
      }
      .thread-title {
        display: flex;
        flex-direction: column;
        gap: 5px;
        min-width: 0;
      }
      .key-line {
        color: var(--muted);
        font-size: 12px;
      }
      .messages {
        padding: 20px 22px;
      }
      .message-group {
        max-width: 860px;
        margin: 0 auto 18px;
      }
      .bubble {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: var(--panel);
        box-shadow: var(--shadow);
        overflow: hidden;
      }
      .bubble.user {
        margin-left: auto;
        max-width: 720px;
        border-color: #dbeafe;
        background: #ffffff;
      }
      .bubble-header {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        justify-content: space-between;
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
      }
      .bubble-body {
        padding: 12px;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }
      .event {
        margin-top: 8px;
        border-left: 2px solid var(--border-strong);
        padding: 8px 0 8px 12px;
      }
      .event.progress {
        border-color: var(--accent);
      }
      .event.question {
        border-color: var(--warning);
        background: linear-gradient(90deg, var(--warning-soft), transparent 60%);
      }
      .event.result {
        border-color: var(--success);
      }
      .event-title {
        font-weight: 600;
      }
      .event-text {
        margin-top: 4px;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
      }
      .artifact-list {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 8px;
      }
      .composer {
        padding: 14px 18px;
        border-top: 1px solid var(--border);
        background: var(--panel);
      }
      .composer-inner {
        max-width: 860px;
        margin: 0 auto;
      }
      .composer-footer {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: space-between;
        align-items: center;
        margin-top: 10px;
      }
      .inspector-section {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: var(--panel);
        box-shadow: var(--shadow);
        margin-bottom: 12px;
        overflow: hidden;
      }
      .inspector-section h2 {
        margin: 0;
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
        background: var(--panel-subtle);
      }
      .kv {
        display: grid;
        grid-template-columns: 112px minmax(0, 1fr);
        gap: 7px 10px;
        padding: 12px;
        font-size: 12px;
      }
      .kv dt {
        color: var(--muted);
      }
      .kv dd {
        margin: 0;
        min-width: 0;
        overflow-wrap: anywhere;
      }
      .empty {
        padding: 12px;
        color: var(--muted);
        border: 1px dashed var(--border-strong);
        border-radius: 10px;
        background: var(--panel-subtle);
      }
      .error {
        color: var(--danger);
      }
      pre.code {
        margin: 0;
        padding: 12px;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        color: var(--foreground);
        background: var(--panel-subtle);
        font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }
      @media (max-width: 1080px) {
        .app {
          grid-template-columns: 260px minmax(0, 1fr);
        }
        .inspector {
          grid-column: 1 / -1;
          min-height: 360px;
          border-left: 0;
          border-top: 1px solid var(--border);
        }
      }
      @media (max-width: 760px) {
        .app {
          display: block;
        }
        .sidebar, .thread, .inspector {
          min-height: auto;
          border: 0;
          border-bottom: 1px solid var(--border);
        }
        .messages {
          max-height: none;
          padding: 14px;
        }
        .kv {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <main class="app">
      <aside class="sidebar">
        <div class="side-header">
          <div class="row between">
            <div>
              <h1>Agent Relay</h1>
              <div class="subtle">Workspace Agent callback inbox</div>
            </div>
            <button id="refreshConversations" type="button" title="Refresh">Refresh</button>
          </div>
        </div>
        <div class="side-scroll">
          <div class="stack">
            <div class="field token-box">
              <label for="authToken">API token</label>
              <input id="authToken" type="password" autocomplete="off" placeholder="Bearer token">
            </div>
          </div>
          <h2>Agents</h2>
          <div id="agents" class="empty">No agents loaded.</div>
          <div class="row between">
            <h2>Conversations</h2>
            <button id="newConversation" class="ghost" type="button">New</button>
          </div>
          <div id="conversations" class="empty">No conversations loaded.</div>
        </div>
      </aside>
      <section class="thread">
        <header class="thread-header">
          <div class="row between">
            <div class="thread-title">
              <h1 id="conversationTitle">No conversation selected.</h1>
              <div class="key-line">
                Continuation key:
                <span id="continuationKey" class="mono">No conversation selected.</span>
              </div>
              <div class="key-line">
                Recent conversation URL:
                <span id="recentConversationUrl" class="mono">No trigger accepted yet.</span>
              </div>
            </div>
            <span id="runCount" class="badge">0 runs</span>
          </div>
        </header>
        <div id="messages" class="messages">
          <div class="empty">No runs loaded.</div>
        </div>
        <footer class="composer">
          <div class="composer-inner">
            <label for="task">Message</label>
            <textarea id="task" placeholder="Send a task to the selected Workspace Agent conversation."></textarea>
            <div class="composer-footer">
              <div class="key-line">
                Sends to <span id="composerKey" class="mono">No conversation selected.</span>
              </div>
              <button class="primary" id="sendRun" type="button">Send</button>
            </div>
          </div>
        </footer>
      </section>
      <aside class="inspector">
        <div class="inspector-header">
          <h1>Run inspector</h1>
          <div id="inspectorSubtitle" class="subtle">Select a run to inspect callback data.</div>
        </div>
        <div id="details" class="inspector-scroll">
          <div class="empty">No run selected.</div>
        </div>
      </aside>
    </main>
    <script>
      const TERMINAL_STATUSES = new Set(['done', 'blocked', 'failed']);
      let selectedConversationId = null;
      let selectedRunId = null;
      let conversationsById = new Map();
      let currentAgents = [];
      let currentRunDetails = [];

      async function api(path, options = {}) {
        const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
        const token = (sessionStorage.getItem('relayAuthToken') || document.getElementById('authToken')?.value || '').trim();
        if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(path, { ...options, headers });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      }

      function clearElement(element) {
        while (element.firstChild) element.removeChild(element.firstChild);
      }

      function text(value) {
        return document.createTextNode(value == null ? '' : String(value));
      }

      function el(tagName, options = {}, children = []) {
        const node = document.createElement(tagName);
        for (const [key, value] of Object.entries(options)) {
          if (key === 'className') node.className = value;
          else if (key === 'textContent') node.textContent = value;
          else if (key === 'title') node.title = value;
          else if (key === 'type') node.type = value;
          else if (key === 'ariaSelected') node.setAttribute('aria-selected', value ? 'true' : 'false');
          else if (key.startsWith('data')) node.dataset[key.slice(4).toLowerCase()] = value;
          else node.setAttribute(key, value);
        }
        for (const child of children) {
          node.appendChild(typeof child === 'string' ? text(child) : child);
        }
        return node;
      }

      function statusBadge(status) {
        return el('span', { className: `badge ${status || ''}`, textContent: status || 'unknown' });
      }

      function formatTime(value) {
        if (!value) return 'n/a';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString();
      }

      function renderEmpty(element, message) {
        clearElement(element);
        element.appendChild(el('div', { className: 'empty', textContent: message }));
      }

      function renderError(message) {
        const details = document.getElementById('details');
        clearElement(details);
        details.appendChild(el('div', { className: 'empty error', textContent: message }));
      }

      async function bootstrap() {
        try {
          let agents = await api('/api/agents');
          if (agents.length === 0) {
            await api('/api/agents', {
              method: 'POST',
              body: JSON.stringify({
                name: 'default',
                trigger_url: '',
                token_ref: 'env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN'
              })
            });
            agents = await api('/api/agents');
          }
          currentAgents = agents;
          renderAgents(agents);

          let conversations = await api('/api/conversations');
          if (conversations.length === 0) {
            const key = 'default:' + new Date().toISOString().slice(0, 10);
            await api('/api/conversations', {
              method: 'POST',
              body: JSON.stringify({ agent_id: agents[0].id, name: 'Default', conversation_key: key })
            });
            conversations = await api('/api/conversations');
          }

          conversationsById = new Map(conversations.map((item) => [item.id, item]));
          renderConversations(conversations);
          selectedConversationId = selectedConversationId || conversations[0]?.id || null;
          await loadRuns();
        } catch (error) {
          renderError(String(error));
        }
      }

      function renderAgents(agents) {
        const container = document.getElementById('agents');
        if (agents.length === 0) {
          renderEmpty(container, 'No agents loaded.');
          return;
        }
        clearElement(container);
        for (const agent of agents) {
          container.appendChild(
            el('div', { className: 'item' }, [
              el('span', { className: 'item-title', textContent: agent.name }),
              el('span', { className: 'item-meta mono', textContent: agent.trigger_id || 'No trigger id' }),
            ])
          );
        }
      }

      function renderConversations(conversations) {
        const container = document.getElementById('conversations');
        if (conversations.length === 0) {
          renderEmpty(container, 'No conversations loaded.');
          return;
        }
        clearElement(container);
        for (const item of conversations) {
          const button = el('button', {
            className: 'item',
            type: 'button',
            ariaSelected: item.id === selectedConversationId,
          });
          button.addEventListener('click', () => selectConversation(item.id));
          button.appendChild(el('span', { className: 'item-title', textContent: item.name }));
          button.appendChild(el('span', { className: 'item-meta mono', textContent: item.conversation_key }));
          container.appendChild(button);
        }
      }

      async function selectConversation(id) {
        selectedConversationId = id;
        await loadRuns();
      }

      async function loadRuns() {
        if (!selectedConversationId) {
          renderEmpty(document.getElementById('messages'), 'No conversation selected.');
          return;
        }
        const conversation = conversationsById.get(selectedConversationId);
        const key = conversation ? conversation.conversation_key : 'No conversation selected.';
        document.getElementById('conversationTitle').textContent = conversation ? conversation.name : 'No conversation selected.';
        document.getElementById('continuationKey').textContent = key;
        document.getElementById('composerKey').textContent = key;
        const runs = await api(`/api/conversations/${selectedConversationId}/runs`);
        const details = await Promise.all(
          runs.map((run) => api(`/api/runs/${run.id}`).catch(() => ({ run, events: [], artifacts: [] })))
        );
        currentRunDetails = details;
        const recentUrl = runs.find((run) => run.conversation_url)?.conversation_url;
        document.getElementById('recentConversationUrl').textContent = recentUrl || 'No trigger accepted yet.';
        document.getElementById('runCount').textContent = `${runs.length} ${runs.length === 1 ? 'run' : 'runs'}`;
        renderConversations(Array.from(conversationsById.values()));
        renderMessages(details);
        if (selectedRunId) {
          const selected = details.find((detail) => detail.run.id === selectedRunId);
          if (selected) renderInspector(selected);
        }
      }

      function renderMessages(details) {
        const container = document.getElementById('messages');
        if (details.length === 0) {
          renderEmpty(container, 'No runs yet.');
          return;
        }
        clearElement(container);
        for (const detail of [...details].reverse()) {
          container.appendChild(renderRunMessage(detail));
        }
      }

      function renderRunMessage(detail) {
        const run = detail.run;
        const group = el('div', { className: 'message-group' });
        const userBubble = el('article', { className: 'bubble user' }, [
          el('div', { className: 'bubble-header' }, [
            el('strong', { textContent: 'You' }),
            statusBadge(run.status),
          ]),
          el('div', { className: 'bubble-body', textContent: run.input_markdown || '(empty message)' }),
        ]);
        const agentBubble = el('article', { className: 'bubble' }, [
          el('div', { className: 'bubble-header' }, [
            el('strong', { textContent: 'Workspace Agent' }),
            el('button', { type: 'button', textContent: 'Inspect' }),
          ]),
        ]);
        agentBubble.querySelector('button').addEventListener('click', () => {
          selectedRunId = run.id;
          renderInspector(detail);
        });
        const body = el('div', { className: 'bubble-body' });
        if (!detail.events.length) {
          body.appendChild(el('div', { className: 'subtle', textContent: `Trigger ${run.trigger_status || run.status || 'pending'}. Waiting for callback events.` }));
        } else {
          for (const event of detail.events) {
            body.appendChild(renderEvent(event));
          }
        }
        if (detail.artifacts.length) {
          body.appendChild(renderArtifacts(detail.artifacts));
        }
        agentBubble.appendChild(body);
        group.appendChild(userBubble);
        group.appendChild(agentBubble);
        return group;
      }

      function renderEvent(event) {
        const kind = event.event_type || 'event';
        const node = el('div', { className: `event ${kind}` }, [
          el('div', { className: 'row between' }, [
            el('div', { className: 'event-title', textContent: event.title || kind }),
            el('span', { className: 'badge', textContent: kind }),
          ]),
        ]);
        if (event.markdown) {
          node.appendChild(el('div', { className: 'event-text', textContent: event.markdown }));
        }
        return node;
      }

      function renderArtifacts(artifacts) {
        const list = el('div', { className: 'artifact-list' });
        for (const artifact of artifacts) {
          list.appendChild(el('span', { className: 'badge', textContent: artifact.name || 'artifact' }));
        }
        return list;
      }

      async function showRun(run) {
        selectedRunId = run.id;
        const detail = await api(`/api/runs/${run.id}`);
        renderInspector(detail);
      }

      function renderInspector(detail) {
        const run = detail.run;
        const details = document.getElementById('details');
        document.getElementById('inspectorSubtitle').textContent = run.request_id;
        clearElement(details);
        details.appendChild(renderKvSection('Run', [
          ['status', run.status],
          ['request_id', run.request_id],
          ['conversation_key', run.conversation_key],
          ['created_at', formatTime(run.created_at)],
          ['completed_at', formatTime(run.completed_at)],
        ]));
        details.appendChild(renderKvSection('Trigger', [
          ['idempotency_key', run.idempotency_key],
          ['trigger_status', run.trigger_status],
          ['http_status', run.trigger_http_status],
          ['x_request_id', run.trigger_x_request_id],
          ['conversation_url', run.conversation_url],
        ]));
        details.appendChild(renderListSection('Events', detail.events, (event) => [
          event.event_type || 'event',
          event.title || '',
          event.markdown || '',
        ]));
        details.appendChild(renderListSection('Artifacts', detail.artifacts, (artifact) => [
          artifact.name || 'artifact',
          artifact.mime_type || '',
          artifact.content || '',
        ]));
        details.appendChild(renderJsonSection('Raw JSON', detail));
      }

      function renderKvSection(title, rows) {
        const dl = el('dl', { className: 'kv' });
        for (const [key, value] of rows) {
          dl.appendChild(el('dt', { textContent: key }));
          dl.appendChild(el('dd', { className: 'mono', textContent: value || 'n/a' }));
        }
        return el('section', { className: 'inspector-section' }, [
          el('h2', { textContent: title }),
          dl,
        ]);
      }

      function renderListSection(title, items, getLines) {
        const section = el('section', { className: 'inspector-section' }, [
          el('h2', { textContent: title }),
        ]);
        if (!items.length) {
          section.appendChild(el('div', { className: 'empty', textContent: `No ${title.toLowerCase()}.` }));
          return section;
        }
        const box = el('div', { className: 'stack' });
        box.style.padding = '12px';
        for (const item of items) {
          const lines = getLines(item).filter(Boolean);
          box.appendChild(el('div', { className: 'token-box' }, lines.map((line, index) =>
            el('div', { className: index === 0 ? 'event-title' : 'event-text', textContent: line })
          )));
        }
        section.appendChild(box);
        return section;
      }

      function renderJsonSection(title, value) {
        return el('section', { className: 'inspector-section' }, [
          el('h2', { textContent: title }),
          el('pre', { className: 'code', textContent: JSON.stringify(value, null, 2) }),
        ]);
      }

      async function sendRun() {
        if (!selectedConversationId) await bootstrap();
        const input = document.getElementById('task').value;
        if (!input.trim()) return;
        const run = await api(`/api/conversations/${selectedConversationId}/runs`, {
          method: 'POST',
          body: JSON.stringify({ input_markdown: input })
        });
        document.getElementById('task').value = '';
        await showRun(run);
        await loadRuns();
      }

      async function createConversation() {
        const agents = currentAgents.length ? currentAgents : await api('/api/agents');
        if (!agents.length) throw new Error('No agent is configured.');
        const name = prompt('Conversation name', 'New conversation');
        if (!name) return;
        const defaultKey = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, ':').replace(/^:|:$/g, '') || 'conversation';
        const key = prompt('Stable conversation_key', `${defaultKey}:${new Date().toISOString().slice(0, 10)}`);
        if (!key) return;
        const conversation = await api('/api/conversations', {
          method: 'POST',
          body: JSON.stringify({ agent_id: agents[0].id, name, conversation_key: key })
        });
        selectedConversationId = conversation.id;
        await bootstrap();
      }

      document.getElementById('refreshConversations').addEventListener('click', () => {
        bootstrap().catch((error) => renderError(String(error)));
      });
      document.getElementById('sendRun').addEventListener('click', () => {
        sendRun().catch((error) => renderError(String(error)));
      });
      document.getElementById('newConversation').addEventListener('click', () => {
        createConversation().catch((error) => renderError(String(error)));
      });
      document.getElementById('authToken').addEventListener('input', (event) => {
        sessionStorage.setItem('relayAuthToken', event.target.value.trim());
      });
      document.getElementById('authToken').value = sessionStorage.getItem('relayAuthToken') || '';
      bootstrap().catch((error) => renderError(String(error)));
      setInterval(() => loadRuns().catch((error) => renderError(String(error))), 3000);
    </script>
  </body>
</html>
""".strip()


def build_app(
    *,
    mcp: Any,
    streamable_app: Any,
    legacy_sse_app: Any,
    store: Any,
    config: Any,
    get_auth_token: Callable[[], str],
    get_oauth_config: Callable[[], Any],
    get_debug_enabled: Callable[[], bool],
    instructions: str,
) -> Starlette:
    mcp_app = build_http_compat_app(
        streamable_app=streamable_app,
        legacy_sse_app=legacy_sse_app,
        app_name="workspace-agent-relay-mcp",
        mcp_path="/mcp",
        get_auth_token=get_auth_token,
        get_oauth_config=get_oauth_config,
        get_debug_enabled=get_debug_enabled,
        instructions=instructions,
    )

    def current_oauth_manager() -> OAuthManager:
        return OAuthManager(get_oauth_config(), mcp_path="/mcp")

    async def dashboard(_: Request) -> HTMLResponse:
        return HTMLResponse(_dashboard_html())

    async def list_agents(_: Request) -> JSONResponse:
        return JSONResponse(store.list_agents())

    async def create_agent(request: Request) -> JSONResponse:
        try:
            payload = await _json(request)
        except ValueError as exc:
            return _json_error(str(exc), status_code=400)
        trigger_url = str(payload.get("trigger_url") or config.default_trigger_url)
        if not trigger_url:
            return _json_error("trigger_url is required")
        token_ref = str(payload.get("token_ref") or SUPPORTED_AGENT_TOKEN_REF)
        try:
            _validate_trigger_url(trigger_url)
            _validate_agent_token_ref(token_ref)
        except ValueError as exc:
            return _json_error(str(exc), status_code=400)
        agent = store.upsert_agent(
            name=str(payload.get("name") or config.default_agent_name),
            trigger_url=trigger_url,
            token_ref=token_ref,
        )
        return JSONResponse(agent)

    async def list_conversations(_: Request) -> JSONResponse:
        return JSONResponse(store.list_conversations())

    async def create_conversation(request: Request) -> JSONResponse:
        try:
            payload = await _json(request)
        except ValueError as exc:
            return _json_error(str(exc), status_code=400)
        missing = _missing_fields(payload, ("agent_id", "name", "conversation_key"))
        if missing:
            return _json_error(f"missing required field(s): {', '.join(missing)}")
        try:
            conversation = store.create_conversation(
                agent_id=int(payload["agent_id"]),
                name=str(payload["name"]),
                conversation_key=str(payload["conversation_key"]),
            )
        except (KeyError, ValueError, sqlite3.IntegrityError) as exc:
            return _json_error(str(exc), status_code=400)
        return JSONResponse(conversation)

    async def list_runs(request: Request) -> JSONResponse:
        try:
            conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        except KeyError as exc:
            return _json_error(str(exc), status_code=404)
        return JSONResponse(store.list_runs_for_conversation(int(conversation["id"])))

    async def get_run_detail(request: Request) -> JSONResponse:
        run_id = int(request.path_params["run_id"])
        try:
            run = store.get_run(run_id)
        except KeyError as exc:
            return _json_error(str(exc), status_code=404)
        return JSONResponse(
            {
                "run": run,
                "events": store.list_events(run_id),
                "artifacts": store.list_artifacts(run_id),
            }
        )

    async def create_run(request: Request) -> JSONResponse:
        try:
            payload = await _json(request)
        except ValueError as exc:
            return _json_error(str(exc), status_code=400)
        try:
            conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        except KeyError as exc:
            return _json_error(str(exc), status_code=404)
        agents = store.list_agents()
        try:
            agent = next(item for item in agents if int(item["id"]) == int(conversation["agent_id"]))
        except StopIteration:
            return _json_error("conversation agent was not found", status_code=404)
        trigger_url = str(agent["trigger_url"])
        try:
            _validate_trigger_url(trigger_url)
            access_token = _agent_token(config, str(agent["token_ref"]))
        except ValueError as exc:
            return _json_error(str(exc), status_code=400)
        request_id = generate_request_id()
        idempotency_key = generate_request_id("idem")
        callback_token = generate_callback_token()
        input_markdown = str(payload.get("input_markdown") or "")
        conversation_key = str(conversation["conversation_key"])
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=conversation_key,
            callback_token=callback_token,
            user_input=input_markdown,
        )
        store.create_run(
            agent_id=int(agent["id"]),
            conversation_id=int(conversation["id"]),
            conversation_key=conversation_key,
            input_markdown=input_markdown,
            callback_token=callback_token,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        trigger_client = getattr(request.app.state, "trigger_client", None) or TriggerClient()
        try:
            trigger_result = await run_in_threadpool(
                trigger_client.trigger,
                trigger_url=trigger_url,
                access_token=access_token,
                conversation_key=conversation_key,
                input_text=trigger_input,
                idempotency_key=idempotency_key,
            )
        except Exception:
            run = store.update_run_trigger_result(
                request_id=request_id,
                trigger_http_status=0,
                trigger_x_request_id=None,
                conversation_url=None,
            )
            return JSONResponse(
                {"success": False, "error": "trigger request failed", "run": run},
                status_code=502,
            )
        run = store.update_run_trigger_result(
            request_id=request_id,
            trigger_http_status=trigger_result.http_status,
            trigger_x_request_id=trigger_result.x_request_id,
            conversation_url=trigger_result.conversation_url,
        )
        return JSONResponse(run)

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = Starlette(
        routes=[
            Route("/", endpoint=dashboard, methods=["GET"]),
            Route("/api/agents", endpoint=list_agents, methods=["GET"]),
            Route("/api/agents", endpoint=create_agent, methods=["POST"]),
            Route("/api/conversations", endpoint=list_conversations, methods=["GET"]),
            Route("/api/conversations", endpoint=create_conversation, methods=["POST"]),
            Route("/api/conversations/{conversation_id:int}/runs", endpoint=list_runs, methods=["GET"]),
            Route("/api/conversations/{conversation_id:int}/runs", endpoint=create_run, methods=["POST"]),
            Route("/api/runs/{run_id:int}", endpoint=get_run_detail, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        middleware=[
            StarletteMiddleware(
                APIBearerAuthMiddleware,
                get_auth_token=get_auth_token,
                get_oauth_config=get_oauth_config,
                get_oauth_manager=current_oauth_manager,
            )
        ],
        lifespan=lifespan,
    )
    app.state.trigger_client = TriggerClient()
    return app
