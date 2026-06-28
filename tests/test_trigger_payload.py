from io import BytesIO
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request

from workspace_agent_relay_mcp.trigger import (
    TriggerClient,
    TriggerResult,
    build_trigger_input,
    generate_request_id,
)


def test_generate_ids_are_prefixed_and_distinct() -> None:
    first = generate_request_id("relay")
    second = generate_request_id("relay")

    assert first.startswith("relay_")
    assert second.startswith("relay_")
    assert first != second
    assert re.match(r"^relay_\d{8}T\d{6}Z_[0-9a-f]{12}$", first)


def test_build_trigger_input_contains_completion_contract() -> None:
    rendered = build_trigger_input(
        request_id="relay_123",
        conversation_key="research:sherlog",
        user_input="Please research sherlog.",
    )

    assert "request_id: relay_123" in rendered
    assert "conversation_key: research:sherlog" in rendered
    assert "callback_token" not in rendered
    assert "record_result" in rendered
    assert "Do not only answer in the ChatGPT conversation." in rendered
    assert "Keep record_plan user-visible" in rendered
    assert "If notion-local-ops-mcp is unavailable" in rendered
    assert rendered.endswith("Please research sherlog.")


def test_build_trigger_input_continuation_is_compact() -> None:
    """A follow-up turn in the same conversation skips the full ~250-token
    contract and restates one reminder line, to avoid bloating every turn."""
    rendered = build_trigger_input(
        request_id="relay_456",
        conversation_key="research:sherlog",
        user_input="Now add tests.",
        is_continuation=True,
    )

    assert "request_id: relay_456" in rendered
    assert "callback_token" not in rendered
    assert "Same relay protocol as before" in rendered
    assert "Keep record_plan user-visible" in rendered
    assert "If notion-local-ops-mcp is unavailable" in rendered
    assert rendered.endswith("Now add tests.")
    # Continuation must NOT carry the full contract header.
    assert "Completion contract:" not in rendered
    assert "Do not only answer in the ChatGPT conversation." not in rendered


def test_build_trigger_input_steer_reuses_request_id_for_same_turn() -> None:
    """A mid-turn follow-up (steer) reuses the same request_id and asks the
    agent to continue the current turn (record_plan revision) rather than start
    over. No callback_token is involved."""
    rendered = build_trigger_input(
        request_id="relay_789",
        conversation_key="research:sherlog",
        user_input="You didn't push.",
        mode="steer",
    )

    assert "request_id: relay_789" in rendered
    assert "conversation_key: research:sherlog" in rendered
    assert "callback_token" not in rendered
    # Steer must reference same-turn continuation and plan revision.
    assert "SAME turn" in rendered
    assert "freshly rotated" not in rendered
    assert "record_plan" in rendered
    assert "do not start a new turn" in rendered.lower() or "Do NOT start a new turn" in rendered
    assert "Operator added:" in rendered
    assert rendered.endswith("You didn't push.")
    # Steer must NOT carry the initial contract or the continuation reminder.
    assert "Completion contract:" not in rendered
    assert "Same relay protocol as before" not in rendered


def test_build_trigger_input_steer_answer_frames_ask_user_reply() -> None:
    """When answer=True, a steer is the operator's reply to an ask_user on this
    run: it must be framed as the answer (resume the turn) and labeled
    "Operator answered:" — not the generic "Operator added:" guidance framing."""
    rendered = build_trigger_input(
        request_id="relay_789",
        conversation_key="research:sherlog",
        user_input="Target the dev branch.",
        mode="steer",
        answer=True,
    )

    assert "request_id: relay_789" in rendered
    assert "callback_token" not in rendered
    # Answer framing: references ask_user and asks the agent to RESUME the turn.
    assert "ask_user" in rendered
    assert "answer" in rendered.lower()
    assert "Resume the current turn" in rendered
    assert "SAME turn" in rendered
    assert "Operator answered:" in rendered
    assert rendered.endswith("Target the dev branch.")
    # Must NOT use the generic guidance label.
    assert "Operator added:" not in rendered
    # Same steer guardrails apply.
    assert "Do NOT start a new turn" in rendered
    assert "record_plan" in rendered


def test_build_trigger_input_pull_initial() -> None:
    rendered = build_trigger_input(
        request_id="relay_pull_1",
        conversation_key="research:sherlog",
        user_input="Please research sherlog.",
        interaction_mode="pull",
    )

    assert "request_id: relay_pull_1" in rendered
    assert "conversation_key: research:sherlog" in rendered
    assert "relay_mode: pull" in rendered
    assert "relay_mcp:" not in rendered
    assert "workspace-agent-relay-mcp.record_plan" not in rendered
    assert "Completion contract:" not in rendered
    assert "bind_relay_run" in rendered
    assert rendered.endswith("Please research sherlog.")


def test_build_trigger_input_pull_continuation_is_compact() -> None:
    rendered = build_trigger_input(
        request_id="relay_pull_2",
        conversation_key="research:sherlog",
        user_input="Now add tests.",
        is_continuation=True,
        interaction_mode="pull",
    )

    assert "relay_mode: pull" in rendered
    assert "Same pull mode as before" in rendered
    assert "workspace-agent-relay-mcp.record_plan" not in rendered
    assert "Completion contract:" not in rendered
    assert rendered.endswith("Now add tests.")


def test_build_trigger_input_pull_steer_same_turn() -> None:
    rendered = build_trigger_input(
        request_id="relay_pull_3",
        conversation_key="research:sherlog",
        user_input="You didn't push.",
        mode="steer",
        interaction_mode="pull",
    )

    assert "relay_mode: pull" in rendered
    assert "SAME turn" in rendered
    assert "Operator added:" in rendered
    assert "workspace-agent-relay-mcp.record_plan" not in rendered
    assert rendered.endswith("You didn't push.")


def test_build_trigger_input_pull_steer_answer() -> None:
    rendered = build_trigger_input(
        request_id="relay_pull_4",
        conversation_key="research:sherlog",
        user_input="Target the dev branch.",
        mode="steer",
        answer=True,
        interaction_mode="pull",
    )

    assert "relay_mode: pull" in rendered
    assert "Operator answered:" in rendered
    assert "Resume the current turn" in rendered
    assert "workspace-agent-relay-mcp.record_plan" not in rendered
    assert rendered.endswith("Target the dev branch.")


class FakeResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status = status
        self._body = body
        self.headers = headers

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class FakeOpener:
    def __init__(
        self,
        *,
        status: int = 202,
        body: bytes = b'{"conversation_url":"https://chatgpt.com/c/test"}',
        headers: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.headers = headers or {"x-request-id": "req_api_123"}
        self.error = error
        self.request: Request | None = None
        self.timeout: float | None = None

    def open(self, request: Request, timeout: float):
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        return FakeResponse(self.status, self.body, self.headers)


def make_http_error(
    *,
    status: int,
    body: bytes,
    headers: dict[str, str] | None = None,
) -> HTTPError:
    return HTTPError(
        "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        status,
        "error",
        headers or {},
        BytesIO(body),
    )


def test_trigger_client_posts_expected_payload() -> None:
    opener = FakeOpener()
    client = TriggerClient(opener=opener)
    trigger_url = "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger"

    result = client.trigger(
        trigger_url=trigger_url,
        access_token="agent-token",
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.http_status == 202
    assert result.x_request_id == "req_api_123"
    assert result.conversation_url == "https://chatgpt.com/c/test"
    assert opener.request is not None
    assert opener.request.full_url == trigger_url
    assert opener.request.get_method() == "POST"
    assert opener.timeout == 60.0
    assert opener.request.headers["Authorization"] == "Bearer agent-token"
    assert opener.request.headers["Content-type"] == "application/json"
    assert opener.request.headers["Idempotency-key"] == "relay_123"
    body = json.loads(opener.request.data.decode("utf-8"))
    assert body == {"conversation_key": "research:sherlog", "input": "hello"}


def test_trigger_client_returns_raw_body_for_successful_non_json_response() -> None:
    opener = FakeOpener(body=b"accepted but not json")
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token="agent-token",
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.accepted is True
    assert result.http_status == 202
    assert result.conversation_url is None
    assert result.response_body == {"raw": "accepted but not json"}


def test_trigger_client_returns_http_error_json_body_without_access_token_echo() -> None:
    access_token = "agent-token-secret"
    opener = FakeOpener(
        error=make_http_error(
            status=400,
            body=b'{"error":{"message":"bad request agent-token-secret"}}',
            headers={"x-request-id": "req_api_400"},
        )
    )
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token=access_token,
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.accepted is False
    assert result.http_status == 400
    assert result.x_request_id == "req_api_400"
    assert result.conversation_url is None
    assert result.response_body == {"error": {"message": "bad request [REDACTED]"}}
    assert "[REDACTED]" in str(result.error)
    assert access_token not in str(result.response_body)
    assert access_token not in str(result.error)


def test_trigger_client_redacts_access_token_from_http_error_json_keys() -> None:
    access_token = "agent-token-secret"
    opener = FakeOpener(
        error=make_http_error(
            status=400,
            body=b'{"agent-token-secret":"reflected key"}',
            headers={"x-request-id": "req_api_400"},
        )
    )
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token=access_token,
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.response_body == {"[REDACTED]": "reflected key"}
    assert "[REDACTED]" in str(result.error)
    assert access_token not in str(result.response_body)
    assert access_token not in str(result.error)


def test_trigger_client_returns_http_error_raw_body_without_access_token_echo() -> None:
    access_token = "agent-token-secret"
    opener = FakeOpener(
        error=make_http_error(
            status=502,
            body=b"upstream agent-token-secret unavailable",
            headers={"x-request-id": "req_api_502"},
        )
    )
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token=access_token,
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.accepted is False
    assert result.http_status == 502
    assert result.x_request_id == "req_api_502"
    assert result.conversation_url is None
    assert result.response_body == {"raw": "upstream [REDACTED] unavailable"}
    assert "[REDACTED]" in str(result.error)
    assert access_token not in str(result.response_body)
    assert access_token not in str(result.error)


def test_trigger_client_returns_url_error_without_access_token_echo() -> None:
    access_token = "agent-token-secret"
    opener = FakeOpener(error=URLError("connection refused agent-token-secret"))
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token=access_token,
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.accepted is False
    assert result.http_status == 0
    assert result.x_request_id is None
    assert result.conversation_url is None
    assert result.response_body == {}
    # The error preserves the exception type (so URLError vs TimeoutError are
    # distinguishable in the stored trigger_error) and redacts the token.
    assert result.error == "URLError: connection refused [REDACTED]"
    assert access_token not in str(result.response_body)
    assert access_token not in str(result.error)


def test_trigger_client_captures_timeout_error_with_real_reason() -> None:
    # TimeoutError is an OSError subclass, NOT a URLError subclass. Before the
    # fix it bubbled past the `except URLError` handler and surfaced as an
    # opaque "trigger request failed" 502 with http_status=0 and no detail.
    # This is the exact failure mode the Python-urllib User-Agent triggered
    # against the ChatGPT edge (socket read timeout after 60s).
    access_token = "agent-token-secret"
    opener = FakeOpener(error=TimeoutError("The read operation timed out"))
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token=access_token,
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.accepted is False
    assert result.http_status == 0
    assert result.error == "TimeoutError: The read operation timed out"
    assert access_token not in str(result.error)


def test_trigger_client_sends_non_python_urllib_user_agent() -> None:
    # Regression guard: urllib's default User-Agent ("Python-urllib/<ver>")
    # causes the ChatGPT trigger edge to stall until the read timeout with no
    # response bytes. The client must send an explicit, non-Python-urllib UA.
    opener = FakeOpener()
    client = TriggerClient(opener=opener)

    client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token="agent-token",
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert opener.request is not None
    ua = opener.request.headers.get("User-agent")
    assert ua is not None
    assert "Python-urllib" not in ua
    assert ua.startswith("workspace-agent-relay-mcp/")


def test_trigger_result_accepted_reflects_success_status() -> None:
    accepted = TriggerResult(
        http_status=202,
        x_request_id=None,
        conversation_url=None,
        response_body={},
    )
    rejected = TriggerResult(
        http_status=400,
        x_request_id=None,
        conversation_url=None,
        response_body={},
    )

    assert accepted.accepted is True
    assert rejected.accepted is False
