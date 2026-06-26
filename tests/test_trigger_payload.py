from io import BytesIO
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

from workspace_agent_relay_mcp.trigger import (
    TriggerClient,
    TriggerResult,
    build_trigger_input,
    generate_callback_token,
    generate_request_id,
)


def test_generate_ids_are_prefixed_and_distinct() -> None:
    first = generate_request_id("relay")
    second = generate_request_id("relay")
    token = generate_callback_token()

    assert first.startswith("relay_")
    assert second.startswith("relay_")
    assert first != second
    assert len(token) >= 32


def test_build_trigger_input_contains_callback_contract() -> None:
    rendered = build_trigger_input(
        request_id="relay_123",
        conversation_key="research:sherlog",
        callback_token="callback-secret",
        user_input="Please research sherlog.",
    )

    assert "request_id: relay_123" in rendered
    assert "conversation_key: research:sherlog" in rendered
    assert "callback_token: callback-secret" in rendered
    assert "record_result" in rendered
    assert "Do not only answer in the ChatGPT conversation." in rendered
    assert rendered.endswith("Please research sherlog.")


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

    def open(self, request: Request, timeout: float):
        self.request = request
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
    assert result.error == "connection refused [REDACTED]"
    assert access_token not in str(result.response_body)
    assert access_token not in str(result.error)


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
