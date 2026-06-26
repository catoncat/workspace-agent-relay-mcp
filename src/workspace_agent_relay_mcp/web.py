from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from .http_compat import build_http_compat_app
from .trigger import TriggerClient, build_trigger_input, generate_callback_token, generate_request_id


def _json_error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": message}, status_code=status_code)


async def _json(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return payload if isinstance(payload, dict) else {}


def _agent_token(config: Any, token_ref: str) -> str:
    if token_ref == "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN":
        return str(config.default_agent_token)
    return str(config.default_agent_token)


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
        --bg: #f4f7f8;
        --panel: #ffffff;
        --line: #d7dee2;
        --text: #18252b;
        --muted: #5a6870;
        --accent: #0b7a75;
        --accent-strong: #075e5a;
        --warn: #9a5b13;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--text);
        background: var(--bg);
      }
      main {
        display: grid;
        grid-template-columns: minmax(220px, 300px) minmax(360px, 1fr) minmax(260px, 360px);
        min-height: 100vh;
      }
      aside, section {
        padding: 16px;
        border-right: 1px solid var(--line);
      }
      aside:last-child { border-right: 0; }
      h1, h2 {
        margin: 0 0 12px;
        font-weight: 650;
        line-height: 1.2;
      }
      h1 { font-size: 20px; }
      h2 { font-size: 13px; text-transform: uppercase; color: var(--muted); letter-spacing: 0; }
      label { display: block; margin: 12px 0 6px; color: var(--muted); }
      textarea {
        width: 100%;
        min-height: 180px;
        resize: vertical;
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 10px;
        font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        background: var(--panel);
        color: var(--text);
      }
      button {
        min-height: 34px;
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 7px 10px;
        font: inherit;
        color: var(--text);
        background: var(--panel);
        cursor: pointer;
      }
      button.primary {
        border-color: var(--accent);
        background: var(--accent);
        color: #fff;
      }
      button.primary:hover { background: var(--accent-strong); }
      .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
      .item {
        width: 100%;
        margin: 8px 0;
        text-align: left;
      }
      .item small {
        display: block;
        margin-top: 4px;
        color: var(--muted);
        overflow-wrap: anywhere;
      }
      .run {
        border: 1px solid var(--line);
        border-radius: 6px;
        background: var(--panel);
        margin: 8px 0;
        padding: 10px;
      }
      .run button {
        width: 100%;
        text-align: left;
      }
      .meta {
        display: grid;
        gap: 8px;
        margin: 12px 0;
        padding: 10px;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: var(--panel);
      }
      .meta div { min-width: 0; }
      .meta strong { display: block; color: var(--muted); font-size: 12px; }
      .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
      pre {
        min-height: 180px;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: var(--panel);
        padding: 12px;
        margin: 0;
        font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }
      .empty { color: var(--muted); }
      @media (max-width: 860px) {
        main { grid-template-columns: 1fr; }
        aside, section { border-right: 0; border-bottom: 1px solid var(--line); }
      }
    </style>
  </head>
  <body>
    <main>
      <aside>
        <h2>Conversations</h2>
        <div class="toolbar"><button id="refreshConversations" type="button">Refresh</button></div>
        <div id="conversations" class="empty">No conversations loaded.</div>
      </aside>
      <section>
        <h1>Workspace Agent Relay</h1>
        <div class="meta">
          <div>
            <strong>Continuation key</strong>
            <span id="continuationKey" class="mono">No conversation selected.</span>
          </div>
          <div>
            <strong>Recent conversation URL</strong>
            <span id="recentConversationUrl" class="mono">No trigger accepted yet.</span>
          </div>
        </div>
        <label for="task">Message</label>
        <textarea id="task"></textarea>
        <div class="toolbar">
          <button class="primary" id="sendRun" type="button">Send</button>
        </div>
        <h2>Runs</h2>
        <div id="runs" class="empty">No runs loaded.</div>
      </section>
      <aside>
        <h2>Details</h2>
        <pre id="details">No run selected.</pre>
      </aside>
    </main>
    <script>
      let selectedConversationId = null;
      let conversationsById = new Map();

      async function api(path, options = {}) {
        const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
        const response = await fetch(path, { ...options, headers });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      }

      function setDetails(value) {
        document.getElementById('details').textContent =
          typeof value === 'string' ? value : JSON.stringify(value, null, 2);
      }

      async function bootstrap() {
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
        selectedConversationId = selectedConversationId || conversations[0].id;
        await loadRuns();
      }

      function clearElement(element) {
        while (element.firstChild) element.removeChild(element.firstChild);
      }

      function renderEmpty(element, text) {
        clearElement(element);
        const empty = document.createElement('div');
        empty.className = 'empty';
        empty.textContent = text;
        element.appendChild(empty);
      }

      function renderConversations(conversations) {
        const container = document.getElementById('conversations');
        if (conversations.length === 0) {
          renderEmpty(container, 'No conversations loaded.');
          return;
        }
        clearElement(container);
        for (const item of conversations) {
          const button = document.createElement('button');
          button.className = 'item';
          button.type = 'button';
          button.addEventListener('click', () => selectConversation(item.id));
          button.appendChild(document.createTextNode(item.name));
          const key = document.createElement('small');
          key.textContent = item.conversation_key;
          button.appendChild(key);
          container.appendChild(button);
        }
      }

      async function selectConversation(id) {
        selectedConversationId = id;
        await loadRuns();
      }

      async function loadRuns() {
        if (!selectedConversationId) return;
        const conversation = conversationsById.get(selectedConversationId);
        document.getElementById('continuationKey').textContent =
          conversation ? conversation.conversation_key : 'No conversation selected.';

        const runs = await api(`/api/conversations/${selectedConversationId}/runs`);
        const recentUrl = runs.find((run) => run.conversation_url)?.conversation_url;
        document.getElementById('recentConversationUrl').textContent = recentUrl || 'No trigger accepted yet.';
        renderRuns(runs);
      }

      function renderRuns(runs) {
        const container = document.getElementById('runs');
        if (runs.length === 0) {
          renderEmpty(container, 'No runs yet.');
          return;
        }
        clearElement(container);
        for (const run of runs) {
          const frame = document.createElement('div');
          frame.className = 'run';
          const button = document.createElement('button');
          button.type = 'button';
          button.addEventListener('click', () => showRun(run));
          const requestId = document.createElement('span');
          requestId.className = 'mono';
          requestId.textContent = run.request_id;
          button.appendChild(requestId);
          button.appendChild(document.createElement('br'));
          button.appendChild(document.createTextNode(`Status: ${run.status}`));
          frame.appendChild(button);
          container.appendChild(frame);
        }
      }

      function showRun(run) {
        setDetails(run);
      }

      async function sendRun() {
        if (!selectedConversationId) await bootstrap();
        const input = document.getElementById('task').value;
        const run = await api(`/api/conversations/${selectedConversationId}/runs`, {
          method: 'POST',
          body: JSON.stringify({ input_markdown: input })
        });
        showRun(run);
        await loadRuns();
      }

      document.getElementById('refreshConversations').addEventListener('click', () => {
        bootstrap().catch((error) => setDetails(String(error)));
      });
      document.getElementById('sendRun').addEventListener('click', () => {
        sendRun().catch((error) => setDetails(String(error)));
      });
      bootstrap().catch((error) => setDetails(String(error)));
      setInterval(() => loadRuns().catch((error) => setDetails(String(error))), 2000);
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

    async def dashboard(_: Request) -> HTMLResponse:
        return HTMLResponse(_dashboard_html())

    async def list_agents(_: Request) -> JSONResponse:
        return JSONResponse(store.list_agents())

    async def create_agent(request: Request) -> JSONResponse:
        payload = await _json(request)
        trigger_url = str(payload.get("trigger_url") or config.default_trigger_url)
        if not trigger_url:
            return _json_error("trigger_url is required")
        agent = store.upsert_agent(
            name=str(payload.get("name") or config.default_agent_name),
            trigger_url=trigger_url,
            token_ref=str(payload.get("token_ref") or "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN"),
        )
        return JSONResponse(agent)

    async def list_conversations(_: Request) -> JSONResponse:
        return JSONResponse(store.list_conversations())

    async def create_conversation(request: Request) -> JSONResponse:
        payload = await _json(request)
        missing = _missing_fields(payload, ("agent_id", "name", "conversation_key"))
        if missing:
            return _json_error(f"missing required field(s): {', '.join(missing)}")
        try:
            conversation = store.create_conversation(
                agent_id=int(payload["agent_id"]),
                name=str(payload["name"]),
                conversation_key=str(payload["conversation_key"]),
            )
        except (KeyError, ValueError) as exc:
            return _json_error(str(exc), status_code=400)
        return JSONResponse(conversation)

    async def list_runs(request: Request) -> JSONResponse:
        try:
            conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        except KeyError as exc:
            return _json_error(str(exc), status_code=404)
        return JSONResponse(store.list_runs_for_conversation(int(conversation["id"])))

    async def create_run(request: Request) -> JSONResponse:
        payload = await _json(request)
        try:
            conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        except KeyError as exc:
            return _json_error(str(exc), status_code=404)
        agents = store.list_agents()
        try:
            agent = next(item for item in agents if int(item["id"]) == int(conversation["agent_id"]))
        except StopIteration:
            return _json_error("conversation agent was not found", status_code=404)
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
        trigger_result = trigger_client.trigger(
            trigger_url=str(agent["trigger_url"]),
            access_token=_agent_token(config, str(agent["token_ref"])),
            conversation_key=conversation_key,
            input_text=trigger_input,
            idempotency_key=idempotency_key,
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
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
    )
    app.state.trigger_client = TriggerClient()
    return app
