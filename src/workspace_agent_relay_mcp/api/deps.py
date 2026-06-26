from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request


async def json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed JSON body") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload
