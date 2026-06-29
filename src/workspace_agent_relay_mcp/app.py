from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable

from starlette.applications import Starlette
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.routing import Mount, Route

from .api.auth import APIBearerAuthMiddleware, InternalBearerAuthMiddleware
from .api.routes.agents import agent_routes
from .api.routes.conversations import conversation_routes
from .api.routes.internal import internal_routes
from .api.routes.runs import run_routes
from .api.routes.settings import settings_routes
from .api.routes.workspaces import workspace_routes
from .api.static import SPAFallbackMiddleware, frontend_dist, serve_index
from .http_compat import build_http_compat_app
from .oauth import OAuthManager
from .store.bus import RunEventBus
from .trigger import TriggerClient
from .trigger_dispatch import TriggerDispatcher


def build_app(
    *,
    mcp: Any,
    streamable_app: Any,
    legacy_sse_app: Any,
    store: Any,
    config: Any,
    event_bus: RunEventBus,
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

    routes: list[Any] = [Route("/", endpoint=serve_index, methods=["GET"])]

    dist = frontend_dist()
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        from starlette.staticfiles import StaticFiles

        routes.append(Mount("/assets", app=StaticFiles(directory=assets_dir), name="assets"))

    for path, handler, methods in agent_routes(store, config):
        routes.append(Route(path, endpoint=handler, methods=methods))
    for path, handler, methods in settings_routes(store):
        routes.append(Route(path, endpoint=handler, methods=methods))
    for path, handler, methods in workspace_routes(store):
        routes.append(Route(path, endpoint=handler, methods=methods))
    for path, handler, methods in conversation_routes(store):
        routes.append(Route(path, endpoint=handler, methods=methods))
    for path, handler, methods in run_routes(store, config, event_bus):
        routes.append(Route(path, endpoint=handler, methods=methods))
    for path, handler, methods in internal_routes(store):
        routes.append(Route(path, endpoint=handler, methods=methods))

    routes.append(Mount("/", app=mcp_app))

    trigger_dispatcher = TriggerDispatcher(store)

    @asynccontextmanager
    async def lifespan(_: Starlette):
        async with mcp_app.router.lifespan_context(mcp_app):
            try:
                yield
            finally:
                await trigger_dispatcher.drain()

    app = Starlette(
        routes=routes,
        middleware=[
            StarletteMiddleware(
                SPAFallbackMiddleware,
                dist_dir=frontend_dist(),
            ),
            StarletteMiddleware(
                APIBearerAuthMiddleware,
                get_auth_token=get_auth_token,
                get_oauth_config=get_oauth_config,
                get_oauth_manager=current_oauth_manager,
            ),
            StarletteMiddleware(
                InternalBearerAuthMiddleware,
                get_auth_token=get_auth_token,
            ),
        ],
        lifespan=lifespan,
    )
    app.state.trigger_client = TriggerClient()
    app.state.trigger_dispatcher = trigger_dispatcher
    app.state.event_bus = event_bus
    return app
