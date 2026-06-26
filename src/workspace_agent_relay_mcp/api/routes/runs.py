from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from ...store.relay_store import TERMINAL_STATUSES
from ...store.bus import RunEventBus
from ...trigger import (
    TriggerClient,
    build_trigger_input,
    generate_callback_token,
    generate_request_id,
    redact_secret,
)
from ..deps import json_body
from ..errors import json_error
from ..validation import agent_token, validate_trigger_url

logger = logging.getLogger("workspace_agent_relay_mcp.trigger")


def _run_detail(store: Any, run_id: int) -> dict[str, Any]:
    return {
        "run": store.get_run(run_id),
        "events": store.list_events(run_id),
        "artifacts": store.list_artifacts(run_id),
        "plan": store.get_plan(run_id),
    }


def run_routes(store: Any, config: Any, event_bus: RunEventBus) -> list[tuple]:
    async def list_runs(request: Request) -> JSONResponse:
        try:
            conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        return JSONResponse(store.list_runs_for_conversation(int(conversation["id"])))

    async def get_run_detail(request: Request) -> JSONResponse:
        run_id = int(request.path_params["run_id"])
        try:
            return JSONResponse(_run_detail(store, run_id))
        except KeyError as exc:
            return json_error(str(exc), status_code=404)

    async def stream_run(request: Request):
        run_id = int(request.path_params["run_id"])
        try:
            initial = _run_detail(store, run_id)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)

        queue = event_bus.subscribe(run_id)

        async def generator():
            try:
                yield f"data: {json.dumps(initial, ensure_ascii=False)}\n\n"
                if initial["run"].get("status") in TERMINAL_STATUSES:
                    return
                while True:
                    try:
                        detail = await asyncio.wait_for(queue.get(), timeout=25.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps(detail, ensure_ascii=False)}\n\n"
                    if detail.get("run", {}).get("status") in TERMINAL_STATUSES:
                        return
            finally:
                event_bus.unsubscribe(run_id, queue)

        return StreamingResponse(generator(), media_type="text/event-stream")

    async def create_run(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        try:
            conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        agents = store.list_agents()
        try:
            agent = next(item for item in agents if int(item["id"]) == int(conversation["agent_id"]))
        except StopIteration:
            return json_error("conversation agent was not found", status_code=404)
        trigger_url = str(agent["trigger_url"])
        try:
            validate_trigger_url(trigger_url)
            access_token = agent_token(config, str(agent["token_ref"]))
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        request_id = generate_request_id()
        idempotency_key = generate_request_id("idem")
        callback_token = generate_callback_token()
        input_markdown = str(payload.get("input_markdown") or "")
        conversation_key = str(conversation["conversation_key"])
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=conversation_key,
            callback_token=callback_token,
            user_input=input_markdown,
        )
        store.create_run(
            agent_id=int(agent["id"]),
            conversation_id=int(conversation["id"]),
            conversation_key=conversation_key,
            input_markdown=input_markdown,
            callback_token=callback_token,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        trigger_client = getattr(request.app.state, "trigger_client", None) or TriggerClient()
        try:
            trigger_result = await run_in_threadpool(
                trigger_client.trigger,
                trigger_url=trigger_url,
                access_token=access_token,
                conversation_key=conversation_key,
                input_text=trigger_input,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            # trigger() normally catches HTTPError/URLError/TimeoutError/OSError
            # itself and returns a TriggerResult. Reaching here means something
            # unexpected blew up (e.g. opener misconfiguration). Preserve the
            # real exception type+message so the failure is diagnosable instead
            # of the old opaque "trigger request failed", but redact the access
            # token in case it leaked into the exception text.
            trigger_error = redact_secret(f"{type(exc).__name__}: {exc}", access_token)
            logger.exception("trigger dispatch raised unexpectedly for request_id=%s", request_id)
            run = store.update_run_trigger_result(
                request_id=request_id,
                trigger_http_status=0,
                trigger_x_request_id=None,
                conversation_url=None,
                trigger_error=trigger_error,
            )
            return JSONResponse(
                {"success": False, "error": "trigger request failed", "detail": trigger_error, "run": run},
                status_code=502,
            )
        run = store.update_run_trigger_result(
            request_id=request_id,
            trigger_http_status=trigger_result.http_status,
            trigger_x_request_id=trigger_result.x_request_id,
            conversation_url=trigger_result.conversation_url,
            trigger_error=trigger_result.error,
        )
        return JSONResponse(run)

    return [
        ("/api/conversations/{conversation_id:int}/runs", list_runs, ["GET"]),
        ("/api/conversations/{conversation_id:int}/runs", create_run, ["POST"]),
        ("/api/runs/{run_id:int}", get_run_detail, ["GET"]),
        ("/api/runs/{run_id:int}/stream", stream_run, ["GET"]),
    ]
