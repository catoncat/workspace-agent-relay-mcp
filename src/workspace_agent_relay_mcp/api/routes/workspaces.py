from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from ...workspace_directories import browse_directory
from ..deps import json_body
from ..errors import json_error
from ..validation import missing_fields


def workspace_routes(store: Any) -> list[tuple]:
    async def list_workspaces(_: Request) -> JSONResponse:
        return JSONResponse(store.list_workspaces())

    async def browse_workspace_directories(request: Request) -> JSONResponse:
        try:
            payload = await run_in_threadpool(
                browse_directory,
                request.query_params.get("path"),
            )
        except PermissionError as exc:
            return json_error(str(exc), status_code=403)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        except OSError as exc:
            return json_error(str(exc), status_code=500)
        return JSONResponse(payload)

    async def pick_workspace_directory(_: Request) -> JSONResponse:
        return json_error(
            "System folder picker is no longer supported. "
            "Use /api/workspaces/browse-directories to browse directories on the relay computer.",
            status_code=410,
        )

    async def create_workspace(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        missing = missing_fields(payload, ("name",))
        if missing:
            return json_error(f"missing required field(s): {', '.join(missing)}")
        try:
            workspace = store.create_workspace(
                name=str(payload["name"]),
                working_directory=payload.get("working_directory"),
            )
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(workspace)

    async def update_workspace(request: Request) -> JSONResponse:
        workspace_id = int(request.path_params["workspace_id"])
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        if not payload:
            return json_error("request body must not be empty", status_code=400)
        allowed = {"name", "working_directory"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return json_error(f"unsupported field(s): {', '.join(unknown)}", status_code=400)
        updates = {key: payload[key] for key in allowed if key in payload}
        try:
            workspace = store.update_workspace(workspace_id, **updates)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(workspace)

    async def delete_workspace(request: Request) -> JSONResponse:
        workspace_id = int(request.path_params["workspace_id"])
        try:
            store.delete_workspace(workspace_id)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        return JSONResponse({"success": True})

    return [
        ("/api/workspaces", list_workspaces, ["GET"]),
        ("/api/workspaces/browse-directories", browse_workspace_directories, ["GET"]),
        ("/api/workspaces/pick-directory", pick_workspace_directory, ["GET", "POST"]),
        ("/api/workspaces", create_workspace, ["POST"]),
        ("/api/workspaces/{workspace_id:int}", update_workspace, ["PATCH"]),
        ("/api/workspaces/{workspace_id:int}", delete_workspace, ["DELETE"]),
    ]
