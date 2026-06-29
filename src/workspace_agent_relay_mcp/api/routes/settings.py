from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error


def settings_routes(store: Any) -> list[tuple]:
    async def get_settings(_: Request) -> JSONResponse:
        return JSONResponse(store.get_settings())

    async def update_settings(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        if not payload:
            return json_error("request body must not be empty", status_code=400)
        allowed = {"current_agent_id", "current_workspace_id"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return json_error(f"unsupported field(s): {', '.join(unknown)}", status_code=400)
        updates: dict[str, int | None] = {}
        try:
            if "current_agent_id" in payload:
                updates["current_agent_id"] = (
                    int(payload["current_agent_id"]) if payload["current_agent_id"] is not None else None
                )
            if "current_workspace_id" in payload:
                updates["current_workspace_id"] = (
                    int(payload["current_workspace_id"]) if payload["current_workspace_id"] is not None else None
                )
            settings = store.update_settings(**updates)
        except (KeyError, ValueError) as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(settings)

    return [
        ("/api/settings", get_settings, ["GET"]),
        ("/api/settings", update_settings, ["PATCH"]),
    ]
