from __future__ import annotations

from typing import Any


def build_app(*, mcp: Any, store: Any, config: Any):
    return mcp.http_app(path="/mcp", transport="streamable-http")
