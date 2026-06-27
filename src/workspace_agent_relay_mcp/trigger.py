from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener


REDACTED_SECRET = "[REDACTED]"

# urllib's default User-Agent is "Python-urllib/<version>". The ChatGPT trigger
# endpoint's edge (Cloudflare) stalls such requests: the TLS+HTTP request is
# sent, but no response bytes are ever returned, so the call hangs until the
# read timeout and surfaces as http_status=0. Use an honest, non-Python-urllib
# User-Agent so the request is treated like any other HTTP client. Confirmed
# empirically: same URL/token/payload with this UA returns 202 in ~7-10s, while
# the default Python-urllib UA hangs for the full 60s timeout.
TRIGGER_USER_AGENT = "workspace-agent-relay-mcp/1.0 (+https://github.com/envvar/workspace-agent-relay-mcp)"


def generate_request_id(prefix: str = "relay") -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{prefix}_{stamp}_{secrets.token_hex(6)}"


def generate_callback_token() -> str:
    return secrets.token_urlsafe(32)


def _redact_secret(value: Any, secret: str) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, REDACTED_SECRET)
    if isinstance(value, dict):
        return {_redact_secret(key, secret): _redact_secret(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret(item, secret) for item in value]
    return value


def redact_secret(value: Any, secret: str) -> Any:
    """Public alias for :func:`_redact_secret` for callers outside this module."""
    return _redact_secret(value, secret)


def build_trigger_input(
    *,
    request_id: str,
    conversation_key: str,
    callback_token: str,
    user_input: str,
    is_continuation: bool = False,
    mode: str = "initial",
) -> str:
    header = [
        f"request_id: {request_id}",
        f"conversation_key: {conversation_key}",
        f"callback_token: {callback_token}",
        "relay_mcp: workspace-agent-relay-mcp",
    ]
    if mode == "steer":
        # Mid-turn follow-up: the operator appended guidance to THIS turn. We can
        # only send triggers, so this is another trigger to the same conversation,
        # bookkept on the same run (same request_id, freshly rotated callback_token
        # above). Ask the agent to continue the current turn rather than start over:
        # revise the plan via record_plan or skip old steps, and keep using the
        # request_id/callback_token above for callbacks. Do NOT call record_result
        # to signal a direction change.
        return "\n".join(
            [
                *header,
                "",
                "This is a follow-up instruction appended to the SAME turn you are already working on (same request_id as before; the callback_token above is freshly rotated — use it for all further callbacks).",
                "Continue the current turn: if the direction changed, call workspace-agent-relay-mcp.record_plan again with the revised steps and/or mark old steps as skipped via record_progress step_updates. Do NOT start a new turn, and do NOT use record_result to signal a plan change.",
                "Keep record_plan user-visible: do not include relay binding, server_info, or routine tool setup as plan steps.",
                "If notion-local-ops-mcp was bound earlier this turn, keep using it; if it is unavailable, still call record_progress/record_result so the operator stays informed.",
                "",
                "Operator added:",
                user_input.strip(),
            ]
        )
    if is_continuation:
        # The agent has already seen the full protocol earlier in this
        # conversation; long sessions may compact it away, so restate just
        # enough to keep the workflow alive without bloating every turn.
        return "\n".join(
            [
                *header,
                "",
                "Same relay protocol as before: record_plan → notion-local-ops-mcp.bind_relay_run → record_progress(step_updates) → record_result, using the new request_id/callback_token above. Keep record_plan user-visible: do not list relay binding, server_info, or routine tool setup as plan steps. If notion-local-ops-mcp is unavailable, skip bind_relay_run and still call record_progress/record_result so the operator stays informed.",
                "",
                "User task:",
                user_input.strip(),
            ]
        )
    return "\n".join(
        [
            *header,
            "",
            "Completion contract:",
            "The local operator CANNOT see your ChatGPT-side plan, tool calls, or reasoning. This relay is their only view of your work.",
            "This trigger starts ONE turn (one request_id + callback_token scope). If the user corrects your direction mid-turn, call record_plan again with the new steps (and/or skip the old ones via record_progress step_updates) — do NOT use record_result to signal a plan change.",
            "Before working, call workspace-agent-relay-mcp.record_plan with your step plan (each step needs a stable id and a title).",
            "Keep record_plan user-visible: do not include relay binding, server_info, or routine tool setup as plan steps unless the user explicitly asked to debug that plumbing.",
            "Then call notion-local-ops-mcp.bind_relay_run with this request_id and the callback_token so your tool calls are mirrored to the operator automatically. You do not need to pass a relay_url; it is already configured locally. If notion-local-ops-mcp is unavailable, skip bind_relay_run and still call record_progress/record_result so the operator stays informed.",
            "After completing several steps, call workspace-agent-relay-mcp.record_progress with step_updates to batch-sync step statuses, optionally with a one-line message summarizing what you did.",
            "If you need a human decision to continue, call workspace-agent-relay-mcp.ask_user (the turn pauses; it is NOT finished).",
            "Call workspace-agent-relay-mcp.record_result exactly once when this turn is truly over: status=done when delivered, status=failed on an execution error, status=blocked ONLY for an external hard blocker (missing access/resource/dependency) — never use blocked to mean 'the plan changed' or 'the user gave a new direction'.",
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
                "User-Agent": TRIGGER_USER_AGENT,
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                try:
                    parsed = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    parsed = {"raw": raw}
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
            parsed = _redact_secret(parsed, access_token)
            return TriggerResult(
                http_status=int(exc.code),
                x_request_id=exc.headers.get("x-request-id"),
                conversation_url=None,
                response_body=parsed if isinstance(parsed, dict) else {},
                error=str(parsed),
            )
        except (URLError, TimeoutError, OSError) as exc:
            # URLError covers most transport failures. TimeoutError (a subclass
            # of OSError, NOT of URLError) is raised on socket read timeouts —
            # which is exactly the failure mode the Python-urllib UA triggers.
            # Catching OSError/TimeoutError explicitly prevents these from
            # bubbling up as opaque "trigger request failed" 502s and preserves
            # the real reason (e.g. "The read operation timed out").
            reason = exc.reason if isinstance(exc, URLError) else exc
            error = _redact_secret(str(reason), access_token)
            return TriggerResult(
                http_status=0,
                x_request_id=None,
                conversation_url=None,
                response_body={},
                error=f"{type(exc).__name__}: {error}",
            )
