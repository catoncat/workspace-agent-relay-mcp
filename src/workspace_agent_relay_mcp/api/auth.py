from __future__ import annotations

import hmac
from typing import Any, Callable

from ..http_compat import HTTPBearerAuthMiddleware
from ..oauth import OAuthManager


class APIBearerAuthMiddleware:
    """Protect /api/* with the same bearer rules as /mcp."""

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


class InternalBearerAuthMiddleware:
    """Protect /internal/* (the notion-local-ops tool-trace bridge) with a
    shared bearer token. This endpoint is not an MCP client and not a dashboard
    route, so it sits outside both /mcp OAuth and /api bearer. It authenticates
    with the same WORKSPACE_AGENT_RELAY_AUTH_TOKEN used by the dashboard shared
    token mode. When no auth_token is configured, the endpoint is disabled
    (403) rather than left unauthenticated — the tool-trace bridge must not
    accept writes from unauthenticated callers (the relay may be tunneled)."""

    def __init__(self, app: Any, *, get_auth_token: Callable[[], str]) -> None:
        self.app = app
        self._get_auth_token = get_auth_token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith("/internal/"):
            await self.app(scope, receive, send)
            return
        expected = (self._get_auth_token() or "").strip()
        if not expected:
            await self._reject(scope, receive, send, status_code=403, message="internal endpoint disabled (no auth_token configured)")
            return
        headers = scope.get("headers") or []
        auth = ""
        for name, value in headers:
            if name == b"authorization":
                auth = value.decode("latin-1")
                break
        token = auth.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        else:
            token = ""
        if not token or not hmac.compare_digest(token, expected):
            await self._reject(scope, receive, send, status_code=401, message="invalid or missing bearer token")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(scope: dict[str, Any], receive: Any, send: Any, *, status_code: int, message: str) -> None:
        from starlette.responses import JSONResponse

        response = JSONResponse({"success": False, "error": message}, status_code=status_code)
        await response(scope, receive, send)
