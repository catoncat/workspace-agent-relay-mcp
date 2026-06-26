from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

# Paths that must NOT be swallowed by the SPA fallback — they belong to MCP,
# OAuth discovery, or API and need to fall through to their own handlers.
_NON_SPA_PREFIXES = ("/api/", "/mcp", "/.well-known", "/assets/", "/messages", "/oauth/")


def frontend_dist() -> Path:
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def mount_frontend(app: Any) -> list[Any]:
    dist = frontend_dist()
    if not dist.is_dir():
        return [_placeholder_route()]

    assets = dist / "assets"
    routes: list[Any] = []
    if assets.is_dir():
        routes.append(StaticFiles(directory=assets, html=False, check_dir=False))

    return routes


async def serve_index(_: Request) -> Response:
    dist = frontend_dist()
    index = dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(_placeholder_html(), status_code=503)


def spa_asgi_app(mcp_app: Any) -> Any:
    """ASGI fallback: serve index.html for SPA deep links, forward MCP/API/etc. to mcp_app."""
    from starlette.requests import Request

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = scope.get("path", "")
        if any(path.startswith(p) for p in _NON_SPA_PREFIXES):
            await mcp_app(scope, receive, send)
            return
        request = Request(scope, receive=receive, send=send)
        response = await serve_index(request)
        await response(scope, receive, send)

    return app


class SPAFallbackMiddleware:
    """Serve index.html for SPA deep links before they hit MCP auth (which 401s).

    GET requests to paths that are not API/MCP/assets/oauth/well-known and not
    a static file (no extension) are served the SPA shell so React Router can
    handle them client-side. Other requests pass through unchanged.
    """

    def __init__(self, app: ASGIApp, *, dist_dir: Path) -> None:
        self.app = app
        self._index = dist_dir / "index.html"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method != "GET" or self._is_system_path(path):
            await self.app(scope, receive, send)
            return
        if self._index.is_file():
            response = FileResponse(self._index)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _is_system_path(path: str) -> bool:
        if any(path.startswith(p) for p in _NON_SPA_PREFIXES):
            return True
        if path == "/" or path == "":
            return True
        # Static files have an extension (e.g. /favicon.svg); let the router handle them.
        if "." in path.rsplit("/", 1)[-1]:
            return True
        return False


async def serve_asset(request: Request) -> Response:
    dist = frontend_dist()
    rel = request.path_params.get("path", "")
    if rel.startswith("api/") or rel.startswith("mcp") or rel.startswith(".well-known"):
        return Response(status_code=404)
    candidate = (dist / rel).resolve()
    try:
        candidate.relative_to(dist.resolve())
    except ValueError:
        return Response(status_code=404)
    if candidate.is_file():
        return FileResponse(candidate)
    index = dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return Response(status_code=404)


def _placeholder_html() -> str:
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>Agent Relay</title></head>
<body><p>Dashboard not built. Run <code>cd frontend && vp build</code>.</p></body></html>"""


def _placeholder_route():
    from starlette.routing import Route

    return Route("/", endpoint=serve_index, methods=["GET"])
