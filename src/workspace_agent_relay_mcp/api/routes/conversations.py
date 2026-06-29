from __future__ import annotations

import sqlite3
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error
from ..validation import missing_fields


def conversation_routes(store: Any) -> list[tuple]:
    async def list_conversations(_: Request) -> JSONResponse:
        return JSONResponse(store.list_conversations())

    async def create_conversation(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        missing = missing_fields(payload, ("agent_id", "name", "conversation_key"))
        if missing:
            return json_error(f"missing required field(s): {', '.join(missing)}")
        try:
            conversation = store.create_conversation(
                agent_id=int(payload["agent_id"]),
                name=str(payload["name"]),
                conversation_key=str(payload["conversation_key"]),
            )
        except (KeyError, ValueError, sqlite3.IntegrityError) as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(conversation)

    async def update_conversation(request: Request) -> JSONResponse:
        conversation_id = int(request.path_params["conversation_id"])
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        if not payload:
            return json_error("request body must not be empty", status_code=400)
        allowed = {"name", "pinned"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return json_error(f"unsupported field(s): {', '.join(unknown)}", status_code=400)
        updates = {key: payload[key] for key in allowed if key in payload}
        if not updates:
            return json_error("at least one of name or pinned is required", status_code=400)
        try:
            conversation = store.update_conversation(conversation_id, **updates)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        return JSONResponse(conversation)

    async def delete_conversation(request: Request) -> JSONResponse:
        conversation_id = int(request.path_params["conversation_id"])
        try:
            store.delete_conversation(conversation_id)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        return JSONResponse({"success": True})

    return [
        ("/api/conversations", list_conversations, ["GET"]),
        ("/api/conversations", create_conversation, ["POST"]),
        ("/api/conversations/{conversation_id:int}", update_conversation, ["PATCH"]),
        ("/api/conversations/{conversation_id:int}", delete_conversation, ["DELETE"]),
    ]
