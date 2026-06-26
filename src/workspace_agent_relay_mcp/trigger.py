from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener


def generate_request_id(prefix: str = "relay") -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{prefix}_{stamp}_{secrets.token_hex(6)}"


def generate_callback_token() -> str:
    return secrets.token_urlsafe(32)


def build_trigger_input(
    *,
    request_id: str,
    conversation_key: str,
    callback_token: str,
    user_input: str,
) -> str:
    return "\n".join(
        [
            f"request_id: {request_id}",
            f"conversation_key: {conversation_key}",
            f"callback_token: {callback_token}",
            "relay_mcp: workspace-agent-relay-mcp",
            "",
            "Completion contract:",
            "Before you finish, call workspace-agent-relay-mcp.record_result with the exact request_id, conversation_key, callback_token, status, title, and full Markdown result.",
            "Use workspace-agent-relay-mcp.record_progress for meaningful progress updates.",
            "Use workspace-agent-relay-mcp.ask_user if you are blocked on a user decision.",
            "Do not only answer in the ChatGPT conversation.",
            "",
            "User task:",
            user_input.strip(),
        ]
    )


@dataclass(frozen=True)
class TriggerResult:
    http_status: int
    x_request_id: str | None
    conversation_url: str | None
    response_body: dict[str, Any]
    error: str | None = None

    @property
    def accepted(self) -> bool:
        return 200 <= self.http_status < 300


class TriggerClient:
    def __init__(self, *, opener: Any | None = None, timeout: float = 60.0) -> None:
        self.opener = opener or build_opener()
        self.timeout = timeout

    def trigger(
        self,
        *,
        trigger_url: str,
        access_token: str,
        conversation_key: str,
        input_text: str,
        idempotency_key: str,
    ) -> TriggerResult:
        payload = {"conversation_key": conversation_key, "input": input_text}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            trigger_url,
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw.strip() else {}
                return TriggerResult(
                    http_status=int(response.status),
                    x_request_id=response.headers.get("x-request-id"),
                    conversation_url=parsed.get("conversation_url") if isinstance(parsed, dict) else None,
                    response_body=parsed if isinstance(parsed, dict) else {},
                )
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return TriggerResult(
                http_status=int(exc.code),
                x_request_id=exc.headers.get("x-request-id"),
                conversation_url=None,
                response_body=parsed if isinstance(parsed, dict) else {},
                error=str(parsed),
            )
        except URLError as exc:
            return TriggerResult(
                http_status=0,
                x_request_id=None,
                conversation_url=None,
                response_body={},
                error=str(exc.reason),
            )
