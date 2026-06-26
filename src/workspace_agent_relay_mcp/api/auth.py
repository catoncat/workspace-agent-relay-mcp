from __future__ import annotations

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
