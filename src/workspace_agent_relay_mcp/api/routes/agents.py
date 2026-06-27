from __future__ import annotations

import sqlite3
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error
from ..validation import (
    SUPPORTED_AGENT_TOKEN_REF,
    agent_token_configured,
    list_configured_token_refs,
    missing_fields,
    validate_agent_token_ref,
    validate_trigger_url,
)


def _serialize_agent(config: Any, store: Any, agent: dict[str, Any]) -> dict[str, Any]:
    return {
        **agent,
        "token_configured": agent_token_configured(config, store, agent),
    }


def agent_routes(store: Any, config: Any) -> list[tuple]:
    async def list_agents(_: Request) -> JSONResponse:
        agents = store.list_agents()
        return JSONResponse([_serialize_agent(config, store, agent) for agent in agents])

    async def list_token_refs(_: Request) -> JSONResponse:
        return JSONResponse(list_configured_token_refs(config))

    async def create_agent(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        name = str(payload.get("name") or config.default_agent_name).strip()
        if not name:
            return json_error("name is required", status_code=400)
        trigger_url = str(payload.get("trigger_url") or config.default_trigger_url).strip()
        if not trigger_url:
            return json_error("trigger_url is required", status_code=400)
        access_token = str(payload.get("access_token") or "").strip()
        token_ref = str(payload.get("token_ref") or "").strip()
        try:
            validate_trigger_url(trigger_url)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        try:
            if access_token:
                agent = store.create_agent(name=name, trigger_url=trigger_url, access_token=access_token)
            else:
                resolved_ref = token_ref or SUPPORTED_AGENT_TOKEN_REF
                validate_agent_token_ref(resolved_ref)
                agent = store.upsert_agent(
                    name=name,
                    trigger_url=trigger_url,
                    token_ref=resolved_ref,
                )
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        except sqlite3.IntegrityError:
            return json_error("An agent with that name already exists", status_code=400)
        return JSONResponse(_serialize_agent(config, store, agent))

    async def update_agent(request: Request) -> JSONResponse:
        agent_id = int(request.path_params["agent_id"])
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        if not payload:
            return json_error("request body must not be empty", status_code=400)
        try:
            agent = store.get_agent(agent_id)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        try:
            if "name" in payload:
                name = str(payload["name"]).strip()
                if not name:
                    return json_error("name must not be empty", status_code=400)
                agent = store.rename_agent(agent_id, name=name)
            if "access_token" in payload:
                access_token = str(payload["access_token"]).strip()
                if not access_token:
                    return json_error("access_token must not be empty", status_code=400)
                store.set_agent_access_token(agent_id, access_token=access_token)
                agent = store.get_agent(agent_id)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        except sqlite3.IntegrityError:
            return json_error("An agent with that name already exists", status_code=400)
        return JSONResponse(_serialize_agent(config, store, agent))

    async def delete_agent(request: Request) -> JSONResponse:
        agent_id = int(request.path_params["agent_id"])
        try:
            store.delete_agent(agent_id)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        return JSONResponse({"success": True})

    return [
        ("/api/agents", list_agents, ["GET"]),
        ("/api/agents/token-refs", list_token_refs, ["GET"]),
        ("/api/agents", create_agent, ["POST"]),
        ("/api/agents/{agent_id:int}", update_agent, ["PATCH"]),
        ("/api/agents/{agent_id:int}", delete_agent, ["DELETE"]),
    ]
