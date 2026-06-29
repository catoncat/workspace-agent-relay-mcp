from __future__ import annotations

import json
import sqlite3
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from ...store.relay_store import TERMINAL_STATUSES, USER_REPLY_STATUSES
from ...store.bus import RunEventBus
from ...trigger import (
    TriggerClient,
    build_trigger_input,
    generate_request_id,
)
from ..deps import json_body
from ..errors import json_error
from ..validation import resolve_agent_token, validate_trigger_url


def _run_detail(store: Any, run_id: int) -> dict[str, Any]:
    return {
        "run": store.get_run(run_id),
        "events": store.list_events(run_id),
        "artifacts": store.list_artifacts(run_id),
        "plan": store.get_plan(run_id),
    }


def run_routes(store: Any, config: Any, event_bus: RunEventBus) -> list[tuple]:
    def schedule_trigger_dispatch(
        request: Request,
        *,
        trigger_client: Any,
        trigger_url: str,
        access_token: str,
        conversation_key: str,
        input_text: str,
        idempotency_key: str,
        request_id: str,
        action: str,
    ) -> None:
        dispatcher = request.app.state.trigger_dispatcher
        dispatcher.schedule(
            dispatcher.dispatch_trigger_result(
                trigger_client=trigger_client,
                trigger_url=trigger_url,
                access_token=access_token,
                conversation_key=conversation_key,
                input_text=input_text,
                idempotency_key=idempotency_key,
                request_id=request_id,
                action=action,
            )
        )

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
        input_markdown = str(payload.get("input_markdown") or "")
        if not input_markdown.strip():
            return json_error("input_markdown must not be empty", status_code=400)
        conversation_key = str(conversation["conversation_key"])
        # Continuation = this conversation already has prior runs, so the agent
        # has seen the full protocol before. A new run no longer supersedes active
        # runs; it is a distinct request_id that ChatGPT can queue behind current
        # work without closing the current relay run locally.
        is_continuation = len(store.list_runs_for_conversation(int(conversation["id"]))) > 0
        try:
            run = store.create_run(
                agent_id=int(agent["id"]),
                conversation_id=int(conversation["id"]),
                conversation_key=conversation_key,
                input_markdown=input_markdown,
                idempotency_key=idempotency_key,
                request_id=request_id,
            )
        except (KeyError, ValueError, sqlite3.IntegrityError) as exc:
            return json_error(str(exc), status_code=400)
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=conversation_key,
            user_input=input_markdown,
            is_continuation=is_continuation,
            working_directory=run.get("working_directory_snapshot"),
        )
        trigger_client = getattr(request.app.state, "trigger_client", None) or TriggerClient()
        run = store.mark_run_trigger_sent(request_id)
        schedule_trigger_dispatch(
            request,
            trigger_client=trigger_client,
            trigger_url=trigger_url,
            access_token=access_token,
            conversation_key=conversation_key,
            input_text=trigger_input,
            idempotency_key=idempotency_key,
            request_id=request_id,
            action="create",
        )
        return JSONResponse(run)

    async def steer_run(request: Request) -> JSONResponse:
        # Operator guides an active run in this conversation (steer). We can only
        # send triggers, so this is another trigger to the same conversation_key,
        # bookkept on the SAME run row: the same request_id is reused, so the
        # agent's callbacks land on the existing run and can update its plan
        # rather than start a new one. If no run is active, return 409 so the
        # frontend can fall back to a queued/new request.
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
        requested_run_id = payload.get("run_id")
        runs = store.list_runs_for_conversation(int(conversation["id"]))
        if requested_run_id is not None:
            try:
                requested_run_id_int = int(requested_run_id)
            except (TypeError, ValueError):
                return json_error("run_id must be an integer when provided", status_code=400)
            active = next((r for r in runs if int(r["id"]) == requested_run_id_int), None)
            if active is None:
                return json_error("run not found in this conversation", status_code=404)
            if active["status"] in TERMINAL_STATUSES:
                return json_error("run is already terminal; send a new request instead", status_code=409)
        else:
            active = next((r for r in runs if r["status"] not in TERMINAL_STATUSES), None)
        if active is None:
            return json_error("no active run to steer; send a new request instead", status_code=409)
        # Steering a run that is paused on ask_user (needs_user) is the operator's
        # ANSWER: it resumes the same turn. Label the trigger accordingly so the
        # agent treats it as an answer to its question, not brand-new guidance.
        is_answer = str(active["status"]) in USER_REPLY_STATUSES
        input_markdown = str(payload.get("input_markdown") or "")
        if not input_markdown.strip():
            return json_error("input_markdown must not be empty", status_code=400)
        conversation_key = str(conversation["conversation_key"])
        request_id = str(active["request_id"])
        idempotency_key = generate_request_id("idem")
        try:
            run = store.steer_run(
                run_id=int(active["id"]),
                user_input=input_markdown,
            )
        except KeyError as exc:
            return json_error(str(exc), status_code=404)
        except ValueError as exc:
            return json_error(str(exc), status_code=409)
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=conversation_key,
            user_input=input_markdown,
            mode="steer",
            answer=is_answer,
            working_directory=run.get("working_directory_snapshot"),
        )
        trigger_client = getattr(request.app.state, "trigger_client", None) or TriggerClient()
        schedule_trigger_dispatch(
            request,
            trigger_client=trigger_client,
            trigger_url=trigger_url,
            access_token=access_token,
            conversation_key=conversation_key,
            input_text=trigger_input,
            idempotency_key=idempotency_key,
            request_id=request_id,
            action="steer",
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
