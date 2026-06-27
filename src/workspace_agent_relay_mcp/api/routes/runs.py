from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from ...store.relay_store import TERMINAL_STATUSES, USER_REPLY_STATUSES
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
from ..validation import resolve_agent_token, validate_trigger_url

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
            access_token = resolve_agent_token(config, store, str(agent["token_ref"]))
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        request_id = generate_request_id()
        idempotency_key = generate_request_id("idem")
        callback_token = generate_callback_token()
        input_markdown = str(payload.get("input_markdown") or "")
        conversation_key = str(conversation["conversation_key"])
        # Continuation = this conversation already has prior runs, so the agent
        # has seen the full protocol before. Send a compact reminder instead of
        # the full contract to avoid bloating context every turn.
        is_continuation = len(store.list_runs_for_conversation(int(conversation["id"]))) > 0
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=conversation_key,
            callback_token=callback_token,
            user_input=input_markdown,
            is_continuation=is_continuation,
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

    async def steer_run(request: Request) -> JSONResponse:
        # Operator appends guidance to the active run in this conversation
        # (steer). We can only send triggers, so this is another trigger to the
        # same conversation_key, bookkept on the SAME run row: the run's
        # callback_token is rotated and the same request_id is reused, so the
        # agent's callbacks land on the existing run and can UPDATE its plan
        # rather than start a new one. If no run is active, return 409 so the
        # frontend falls back to create_run (a new turn).
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
            access_token = resolve_agent_token(config, store, str(agent["token_ref"]))
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        runs = store.list_runs_for_conversation(int(conversation["id"]))
        active = next((r for r in runs if r["status"] not in TERMINAL_STATUSES), None)
        if active is None:
            return json_error("no active run to steer; send a new turn instead", status_code=409)
        # Steering a run that is paused on ask_user (needs_user) is the operator's
        # ANSWER: it resumes the same turn. Label the trigger accordingly so the
        # agent treats it as an answer to its question, not brand-new guidance.
        is_answer = str(active["status"]) in USER_REPLY_STATUSES
        input_markdown = str(payload.get("input_markdown") or "")
        if not input_markdown.strip():
            return json_error("input_markdown must not be empty", status_code=400)
        conversation_key = str(conversation["conversation_key"])
        request_id = str(active["request_id"])
        new_callback_token = generate_callback_token()
        idempotency_key = generate_request_id("idem")
        try:
            run = store.steer_run(
                run_id=int(active["id"]),
                new_callback_token=new_callback_token,
                user_input=input_markdown,
            )
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        except ValueError as exc:
            return json_error(str(exc), status_code=409)
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=conversation_key,
            callback_token=new_callback_token,
            user_input=input_markdown,
            mode="steer",
            answer=is_answer,
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
            trigger_error = redact_secret(f"{type(exc).__name__}: {exc}", access_token)
            logger.exception("steer trigger dispatch raised unexpectedly for request_id=%s", request_id)
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

    async def dismiss_run(request: Request) -> JSONResponse:
        run_id = int(request.path_params["run_id"])
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        note = str(payload.get("note") or "").strip() or None
        try:
            store.dismiss_run(run_id, note=note)
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        except ValueError as exc:
            return json_error(str(exc), status_code=409)
        return JSONResponse(_run_detail(store, run_id))

    return [
        ("/api/conversations/{conversation_id:int}/runs", list_runs, ["GET"]),
        ("/api/conversations/{conversation_id:int}/runs", create_run, ["POST"]),
        ("/api/conversations/{conversation_id:int}/steer", steer_run, ["POST"]),
        ("/api/runs/{run_id:int}", get_run_detail, ["GET"]),
        ("/api/runs/{run_id:int}/stream", stream_run, ["GET"]),
        ("/api/runs/{run_id:int}/dismiss", dismiss_run, ["POST"]),
    ]
