from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..deps import json_body
from ..errors import json_error

# Map store validation error codes to HTTP status codes. These mirror the
# callback-token validation shape used by record_progress/ask_user/record_result.
_TRACE_ERROR_STATUS = {
    "run_not_found": 404,
    "invalid_callback_token": 401,
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
        callback_token = _require_str(payload, "callback_token")
        tool = _require_str(payload, "tool")
        title = _require_str(payload, "title")
        if not (request_id and conversation_key and callback_token and tool and title):
            return json_error(
                "request_id, conversation_key, callback_token, tool, and title are required",
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
            callback_token=callback_token,
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

    return [
        ("/internal/tool-trace", post_tool_trace, ["POST"]),
    ]
