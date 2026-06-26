from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore
from workspace_agent_relay_mcp.trigger import TriggerResult


class FakeTriggerClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def trigger(self, **kwargs: Any) -> TriggerResult:
        self.calls.append(kwargs)
        return TriggerResult(
            http_status=202,
            x_request_id=f"api_req_{len(self.calls)}",
            conversation_url="https://chatgpt.com/c/test",
            response_body={"conversation_url": "https://chatgpt.com/c/test"},
        )


def _client(tmp_path: Path) -> tuple[TestClient, FakeTriggerClient]:
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(
        state_dir=tmp_path / "state",
        default_agent_token="agent-token",
        default_trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
    )
    server.store = RelayStore(server.config.database_path)
    app = server.build_http_app()
    trigger_client = FakeTriggerClient()
    app.state.trigger_client = trigger_client
    return TestClient(app), trigger_client


def _seed_conversation(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    agent = client.post(
        "/api/agents",
        json={
            "name": "default",
            "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
            "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
        },
    ).json()
    conversation = client.post(
        "/api/conversations",
        json={
            "agent_id": agent["id"],
            "name": "Sherlog",
            "conversation_key": "research:sherlog",
        },
    ).json()
    return agent, conversation


def test_api_can_create_agent_and_conversation(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        agent_response = client.post(
            "/api/agents",
            json={
                "name": "default",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
                "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
            },
        )
        conversation_response = client.post(
            "/api/conversations",
            json={
                "agent_id": agent_response.json()["id"],
                "name": "Sherlog",
                "conversation_key": "research:sherlog",
            },
        )

    assert agent_response.status_code == 200
    assert agent_response.json()["trigger_id"] == "agtch_test"
    assert conversation_response.status_code == 200
    assert conversation_response.json()["conversation_key"] == "research:sherlog"


def test_api_send_run_triggers_agent_and_records_metadata(tmp_path: Path) -> None:
    client, trigger_client = _client(tmp_path)

    with client:
        _, conversation = _seed_conversation(client)
        run_response = client.post(
            f"/api/conversations/{conversation['id']}/runs",
            json={"input_markdown": "Research sherlog"},
        )
        runs_response = client.get(f"/api/conversations/{conversation['id']}/runs")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "accepted"
    assert run["trigger_http_status"] == 202
    assert run["trigger_x_request_id"] == "api_req_1"
    assert run["conversation_key"] == "research:sherlog"
    assert run["conversation_url"] == "https://chatgpt.com/c/test"
    assert run["request_id"].startswith("relay_")
    assert run["idempotency_key"].startswith("idem_")
    assert run["idempotency_key"] != run["request_id"]
    assert runs_response.json()[0]["request_id"] == run["request_id"]

    call = trigger_client.calls[0]
    assert call["conversation_key"] == "research:sherlog"
    assert call["idempotency_key"] == run["idempotency_key"]
    assert f"request_id: {run['request_id']}" in call["input_text"]
    assert "conversation_key: research:sherlog" in call["input_text"]
    assert call["input_text"].endswith("Research sherlog")


def test_api_follow_up_reuses_conversation_key_but_generates_new_message_ids(tmp_path: Path) -> None:
    client, trigger_client = _client(tmp_path)

    with client:
        _, conversation = _seed_conversation(client)
        first = client.post(
            f"/api/conversations/{conversation['id']}/runs",
            json={"input_markdown": "First message"},
        ).json()
        second = client.post(
            f"/api/conversations/{conversation['id']}/runs",
            json={"input_markdown": "Second message"},
        ).json()

    assert first["conversation_key"] == "research:sherlog"
    assert second["conversation_key"] == "research:sherlog"
    assert first["request_id"] != second["request_id"]
    assert first["idempotency_key"] != second["idempotency_key"]
    assert [call["conversation_key"] for call in trigger_client.calls] == [
        "research:sherlog",
        "research:sherlog",
    ]
    assert trigger_client.calls[0]["idempotency_key"] == first["idempotency_key"]
    assert trigger_client.calls[1]["idempotency_key"] == second["idempotency_key"]


def test_dashboard_names_continuation_key_and_recent_conversation_url(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Continuation key" in response.text
    assert "Recent conversation URL" in response.text
