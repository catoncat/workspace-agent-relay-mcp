import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from workspace_agent_relay_mcp.trigger import (
    TriggerClient,
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
    def __init__(self) -> None:
        self.request: Request | None = None

    def open(self, request: Request, timeout: float):
        self.request = request
        return FakeResponse(
            202,
            b'{"conversation_url":"https://chatgpt.com/c/test"}',
            {"x-request-id": "req_api_123"},
        )


def test_trigger_client_posts_expected_payload() -> None:
    opener = FakeOpener()
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token="agent-token",
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.http_status == 202
    assert result.x_request_id == "req_api_123"
    assert result.conversation_url == "https://chatgpt.com/c/test"
    assert opener.request is not None
    assert opener.request.get_method() == "POST"
    assert opener.request.headers["Authorization"] == "Bearer agent-token"
    assert opener.request.headers["Content-type"] == "application/json"
    assert opener.request.headers["Idempotency-key"] == "relay_123"
    body = json.loads(opener.request.data.decode("utf-8"))
    assert body == {"conversation_key": "research:sherlog", "input": "hello"}
