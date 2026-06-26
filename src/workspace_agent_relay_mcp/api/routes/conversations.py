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

    return [
        ("/api/conversations", list_conversations, ["GET"]),
        ("/api/conversations", create_conversation, ["POST"]),
    ]
