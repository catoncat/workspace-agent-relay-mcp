from __future__ import annotations

from starlette.responses import JSONResponse


def json_error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": message}, status_code=status_code)
