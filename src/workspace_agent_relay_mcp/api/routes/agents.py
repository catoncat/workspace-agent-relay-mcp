from __future__ import annotations

import sqlite3
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error
from ..validation import (
    SUPPORTED_AGENT_TOKEN_REF,
    list_configured_token_refs,
    validate_agent_token_ref,
    validate_trigger_url,
)


def agent_routes(store: Any, config: Any) -> list[tuple]:
    async def list_agents(_: Request) -> JSONResponse:
        return JSONResponse(store.list_agents())

    async def list_token_refs(_: Request) -> JSONResponse:
        # Returns token_refs that have a non-empty value in the config snapshot,
        # for the "create agent" form's token_ref dropdown. Only refs (env var
        # names) are returned — never the token values themselves.
        return JSONResponse(list_configured_token_refs(config))

    async def create_agent(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        trigger_url = str(payload.get("trigger_url") or config.default_trigger_url)
        if not trigger_url:
            return json_error("trigger_url is required")
        token_ref = str(payload.get("token_ref") or SUPPORTED_AGENT_TOKEN_REF)
        try:
            validate_trigger_url(trigger_url)
            validate_agent_token_ref(token_ref)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        agent = store.upsert_agent(
            name=str(payload.get("name") or config.default_agent_name),
            trigger_url=trigger_url,
            token_ref=token_ref,
        )
        return JSONResponse(agent)

    return [
        ("/api/agents", list_agents, ["GET"]),
        ("/api/agents/token-refs", list_token_refs, ["GET"]),
        ("/api/agents", create_agent, ["POST"]),
    ]
