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
            x_request_id="api_req_123",
            conversation_url="https://chatgpt.com/c/test",
            response_body={"conversation_url": "https://chatgpt.com/c/test"},
        )


class RaisingTriggerClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def trigger(self, **kwargs: Any) -> TriggerResult:
        self.calls.append(kwargs)
        raise RuntimeError("upstream failed with agent-token")


def _client(
    tmp_path: Path,
    *,
    auth_token: str = "",
    trigger_client: Any | None = None,
) -> tuple[TestClient, Any]:
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(
        state_dir=tmp_path / "state",
        auth_token=auth_token,
        default_agent_token="agent-token",
        default_trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
    )
    server.store = RelayStore(server.config.database_path)
    app = server.build_http_app()
    active_trigger_client = trigger_client or FakeTriggerClient()
    app.state.trigger_client = active_trigger_client
    return TestClient(app), active_trigger_client


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


def test_api_uses_default_trigger_url_when_payload_leaves_it_blank(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.post(
            "/api/agents",
            json={
                "name": "default",
                "trigger_url": "",
                "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
            },
        )

    assert response.status_code == 200
    assert response.json()["trigger_url"] == "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger"
    assert response.json()["trigger_id"] == "agtch_test"


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
    assert run["trigger_x_request_id"] == "api_req_123"
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


def test_api_returns_controlled_errors_for_bad_requests(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        bad_conversation = client.post("/api/conversations", json={})
        missing_agent = client.post(
            "/api/conversations",
            json={"agent_id": 999, "name": "Missing", "conversation_key": "missing:agent"},
        )
        _, conversation = _seed_conversation(client)
        duplicate_key = client.post(
            "/api/conversations",
            json={
                "agent_id": conversation["agent_id"],
                "name": "Duplicate",
                "conversation_key": conversation["conversation_key"],
            },
        )
        missing_runs = client.get("/api/conversations/999/runs")
        missing_create_run = client.post(
            "/api/conversations/999/runs",
            json={"input_markdown": "hello"},
        )

    assert bad_conversation.status_code == 400
    assert bad_conversation.json()["success"] is False
    assert missing_agent.status_code == 400
    assert missing_agent.json()["success"] is False
    assert duplicate_key.status_code == 400
    assert duplicate_key.json()["success"] is False
    assert missing_runs.status_code == 404
    assert missing_runs.json()["success"] is False
    assert missing_create_run.status_code == 404
    assert missing_create_run.json()["success"] is False


def test_dashboard_does_not_use_inner_html_for_stored_data(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert ".innerHTML" not in response.text
    assert "onclick=" not in response.text


def test_dashboard_shell_is_public_but_api_requires_bearer_when_auth_token_is_set(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, auth_token="local-secret")
    headers = {"Authorization": "Bearer local-secret"}

    with client:
        agents_missing = client.get("/api/agents")
        dashboard_allowed = client.get("/")
        agents_allowed = client.get("/api/agents", headers=headers)

    assert agents_missing.status_code == 401
    assert dashboard_allowed.status_code == 200
    assert "sessionStorage" in dashboard_allowed.text
    assert "Authorization" in dashboard_allowed.text
    assert agents_allowed.status_code == 200


def test_api_rejects_non_workspace_trigger_url_and_unknown_token_ref(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        bad_url = client.post(
            "/api/agents",
            json={
                "name": "bad",
                "trigger_url": "https://example.com/v1/workspace_agents/agtch_test/trigger",
                "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
            },
        )
        bad_path = client.post(
            "/api/agents",
            json={
                "name": "bad-path",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger/extra",
                "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
            },
        )
        bad_ref = client.post(
            "/api/agents",
            json={
                "name": "bad-ref",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
                "token_ref": "env:OTHER_TOKEN",
            },
        )

    assert bad_url.status_code == 400
    assert bad_url.json()["success"] is False
    assert bad_path.status_code == 400
    assert bad_path.json()["success"] is False
    assert bad_ref.status_code == 400
    assert bad_ref.json()["success"] is False


def test_api_returns_controlled_error_for_malformed_json(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        malformed = client.post(
            "/api/agents",
            content="{",
            headers={"Content-Type": "application/json"},
        )
        non_object = client.post(
            "/api/agents",
            json=[],
        )

    assert malformed.status_code == 400
    assert malformed.json() == {"success": False, "error": "malformed JSON body"}
    assert non_object.status_code == 400
    assert non_object.json() == {"success": False, "error": "JSON body must be an object"}


def test_api_marks_run_failed_when_trigger_client_raises(tmp_path: Path) -> None:
    trigger_client = RaisingTriggerClient()
    client, _ = _client(tmp_path, trigger_client=trigger_client)

    with client:
        _, conversation = _seed_conversation(client)
        response = client.post(
            f"/api/conversations/{conversation['id']}/runs",
            json={"input_markdown": "Research sherlog"},
        )
        runs_response = client.get(f"/api/conversations/{conversation['id']}/runs")

    assert response.status_code == 502
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "trigger request failed"
    assert body["run"]["status"] == "failed"
    assert body["run"]["trigger_http_status"] == 0
    assert "agent-token" not in str(body)
    assert runs_response.json()[0]["status"] == "failed"
    assert trigger_client.calls[0]["conversation_key"] == "research:sherlog"


def test_api_revalidates_stored_trigger_url_before_triggering(tmp_path: Path) -> None:
    client, trigger_client = _client(tmp_path)

    with client:
        from workspace_agent_relay_mcp import server

        agent = server.store.upsert_agent(
            name="bad-stored",
            trigger_url="https://example.com/v1/workspace_agents/agtch_test/trigger",
            token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
        )
        conversation = server.store.create_conversation(
            agent_id=agent["id"],
            name="Bad Stored",
            conversation_key="bad:stored",
        )
        response = client.post(
            f"/api/conversations/{conversation['id']}/runs",
            json={"input_markdown": "Research sherlog"},
        )
        runs = client.get(f"/api/conversations/{conversation['id']}/runs").json()

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert trigger_client.calls == []
    assert runs == []
