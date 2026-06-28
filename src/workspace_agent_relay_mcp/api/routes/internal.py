from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error

# Map store validation error codes to HTTP status codes. These mirror the
# callback validation shape used by record_progress/ask_user/record_result.
_TRACE_ERROR_STATUS = {
    "run_not_found": 404,
    "conversation_mismatch": 401,
    "run_closed": 409,
}


def _require_str(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def internal_routes(store: Any) -> list[tuple]:
    async def post_tool_trace(request: Request) -> JSONResponse:
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)

        request_id = _require_str(payload, "request_id")
        conversation_key = _require_str(payload, "conversation_key")
        tool = _require_str(payload, "tool")
        title = _require_str(payload, "title")
        if not (request_id and conversation_key and tool and title):
            return json_error(
                "request_id, conversation_key, tool, and title are required",
                status_code=400,
            )

        duration_ms = payload.get("duration_ms")
        if duration_ms is not None and not isinstance(duration_ms, (int, float)):
            return json_error("duration_ms must be a number", status_code=400)

        ok_value = payload.get("ok")
        if ok_value is not None and not isinstance(ok_value, bool):
            return json_error("ok must be a boolean", status_code=400)

        result = store.record_tool_trace(
            request_id=request_id,
            conversation_key=conversation_key,
            tool=tool,
            title=title,
            args_summary=payload.get("args_summary"),
            result_summary=payload.get("result_summary"),
            started_at=payload.get("started_at"),
            duration_ms=duration_ms,
            ok=True if ok_value is None else ok_value,
            error=payload.get("error"),
        )
        if not result.get("success"):
            error = result.get("error") or {}
            code = error.get("code") or ""
            message = error.get("message") or "tool trace rejected"
            status_code = _TRACE_ERROR_STATUS.get(code, 400)
            return json_error(message, status_code=status_code)
        return JSONResponse(result, status_code=200)

    async def post_polling_events(request: Request) -> JSONResponse:
        # Polling-derived events from ChatGPT conversation readback (the
        # hermes_poller_cdp path). The poller is a separate process and does NOT
        # write SQLite directly; it POSTs batches here so the server remains the
        # single writer. Auth is the same shared bearer as /internal/tool-trace.
        try:
            payload = await json_body(request)
        except ValueError as exc:
            return json_error(str(exc), status_code=400)
        try:
            run_id = int(request.path_params["run_id"])
        except (KeyError, ValueError, TypeError):
            return json_error("run_id must be an integer", status_code=400)
        events = payload.get("events")
        if not isinstance(events, list):
            return json_error("events must be a list", status_code=400)
        normalized: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                return json_error(f"events[{index}] must be an object", status_code=400)
            source_key = event.get("source_key")
            event_type = event.get("event_type")
            if not (isinstance(source_key, str) and source_key.strip()):
                return json_error(f"events[{index}].source_key is required", status_code=400)
            if event_type not in ("progress", "result"):
                return json_error(
                    f"events[{index}].event_type must be 'progress' or 'result'",
                    status_code=400,
                )
            create_time = event.get("create_time")
            if create_time is not None and not isinstance(create_time, (int, float)):
                return json_error(f"events[{index}].create_time must be a number", status_code=400)
            normalized.append(
                {
                    "source_key": source_key,
                    "event_type": event_type,
                    "title": event.get("title"),
                    "markdown": event.get("markdown"),
                    "payload": event.get("payload") or {},
                    "create_time": create_time,
                }
            )
        try:
            result = store.record_polling_events(
                run_id=run_id,
                events=normalized,
                hermes_conversation_id=_require_str(payload, "hermes_conversation_id"),
            )
        except KeyError:
            return json_error(f"Run not found: {run_id}", status_code=404)
        return JSONResponse(result, status_code=200)

    async def get_polling_targets(request: Request) -> JSONResponse:
        trigger_id = (request.query_params.get("trigger_id") or "").strip()
        if not trigger_id:
            return json_error("trigger_id query parameter is required", status_code=400)
        return JSONResponse(store.get_polling_targets(trigger_id=trigger_id))

    return [
        ("/internal/tool-trace", post_tool_trace, ["POST"]),
        ("/internal/runs/{run_id:int}/polling-events", post_polling_events, ["POST"]),
        ("/internal/polling-targets", get_polling_targets, ["GET"]),
    ]
