from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore
from workspace_agent_relay_mcp.trigger import TriggerResult


def _frontend_bundle_text() -> str:
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    chunks = [(dist / "index.html").read_text(encoding="utf-8")]
    assets = dist / "assets"
    if assets.is_dir():
        for path in sorted(assets.glob("*.js")):
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


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
    agent_tokens: dict[str, str] | None = None,
) -> tuple[TestClient, Any]:
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(
        state_dir=tmp_path / "state",
        auth_token=auth_token,
        default_agent_token="agent-token",
        default_trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        agent_tokens=agent_tokens or {},
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


def test_api_can_rename_and_delete_conversation(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        _, conversation = _seed_conversation(client)
        rename_response = client.patch(
            f"/api/conversations/{conversation['id']}",
            json={"name": "Renamed"},
        )
        delete_response = client.delete(f"/api/conversations/{conversation['id']}")
        list_response = client.get("/api/conversations")
        missing_response = client.delete("/api/conversations/999")

    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Renamed"
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True
    assert list_response.json() == []
    assert missing_response.status_code == 404


def test_api_can_rename_agent(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        agent, _ = _seed_conversation(client)
        rename_response = client.patch(
            f"/api/agents/{agent['id']}",
            json={"name": "Work agent"},
        )
        list_response = client.get("/api/agents")

    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Work agent"
    assert list_response.json()[0]["name"] == "Work agent"


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


def test_dashboard_names_continuation_key_and_recent_conversation_url_actions(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="root"' in response.text
    bundle = _frontend_bundle_text()
    assert "Copy continuation key" in bundle
    assert "Open in ChatGPT" in bundle
    assert "/api/runs/" in bundle


def test_spa_deep_links_serve_index_html_without_auth(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, auth_token="secret")

    with client:
        # Deep links that React Router should handle must return the SPA shell,
        # not a 401 from MCP auth.
        for path in ("/c/123", "/c/123/r/456", "/c/some:conversation_key/r/789"):
            response = client.get(path)
            assert response.status_code == 200, f"{path} -> {response.status_code}"
            assert 'id="root"' in response.text


def test_dashboard_does_not_use_inner_html_for_stored_data(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert ".innerHTML" not in response.text
    assert "onclick=" not in response.text
    assert "dangerouslySetInnerHTML" not in _frontend_bundle_text()


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
        missing_run_detail = client.get("/api/runs/999")
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
    assert missing_run_detail.status_code == 404
    assert missing_run_detail.json()["success"] is False
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
        run_detail_missing = client.get("/api/runs/999")
        dashboard_allowed = client.get("/")
        agents_allowed = client.get("/api/agents", headers=headers)

    assert agents_missing.status_code == 401
    assert run_detail_missing.status_code == 401
    assert dashboard_allowed.status_code == 200
    assert 'id="root"' in dashboard_allowed.text
    bundle = _frontend_bundle_text()
    assert "localStorage" in bundle
    assert "Authorization" in bundle
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
    # The real exception type+message is surfaced for diagnosis (redacted).
    assert "RuntimeError" in body["detail"]
    assert "upstream failed" in body["detail"]
    # Trigger failure is non-terminal (trigger_failed), because the ChatGPT
    # trigger API is async and may still have dispatched the agent even when we
    # got no 202. A live agent's callbacks must still be accepted.
    assert body["run"]["status"] == "trigger_failed"
    assert body["run"]["trigger_http_status"] == 0
    assert body["run"]["trigger_error"] is not None
    assert "RuntimeError" in body["run"]["trigger_error"]
    assert "agent-token" not in str(body)
    assert runs_response.json()[0]["status"] == "trigger_failed"
    assert trigger_client.calls[0]["conversation_key"] == "research:sherlog"


def test_trigger_failed_run_still_accepts_callbacks(tmp_path: Path) -> None:
    """A trigger_failed run is non-terminal, so a live agent that was actually
    dispatched can still write back plan/progress and advance the run instead of
    being rejected with run_closed."""
    client, _ = _client(tmp_path, trigger_client=RaisingTriggerClient())

    with client:
        from workspace_agent_relay_mcp import server

        agent = server.store.upsert_agent(
            name="Sherlog",
            trigger_url="https://example.com/v1/workspace_agents/agtch_test/trigger",
            token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
        )
        conversation = server.store.create_conversation(
            agent_id=agent["id"],
            name="Sherlog",
            conversation_key="research:sherlog",
        )
        callback_token = "secret-callback-token"
        run = server.store.create_run(
            agent_id=agent["id"],
            conversation_id=conversation["id"],
            conversation_key="research:sherlog",
            input_markdown="Research sherlog",
            callback_token=callback_token,
            idempotency_key="idem_tf",
            request_id="run_tf",
        )
        # Simulate the trigger HTTP call failing (no 202).
        run = server.store.update_run_trigger_result(
            request_id="run_tf",
            trigger_http_status=0,
            trigger_x_request_id=None,
            conversation_url=None,
        )
        assert run["status"] == "trigger_failed"

        # A live agent's record_plan must be accepted (not run_closed).
        plan = server.store.record_plan(
            request_id="run_tf",
            conversation_key="research:sherlog",
            callback_token=callback_token,
            steps=[{"id": "s1", "title": "Step one", "status": "in_progress"}],
        )
        assert plan["success"] is True

        # record_progress advances the run to waiting, proving the agent is alive
        # and that trigger_failed did not lock the run out of further callbacks.
        progress = server.store.record_progress(
            request_id="run_tf",
            conversation_key="research:sherlog",
            callback_token=callback_token,
            message="Still working despite trigger failure",
            title="Working",
        )
        assert progress["success"] is True
        assert server.store.get_run(run["id"])["status"] == "waiting"


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


def test_api_run_detail_returns_callback_events_without_secrets(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, auth_token="local-secret")

    with client:
        from workspace_agent_relay_mcp import server

        agent = server.store.upsert_agent(
            name="default",
            trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
            token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
        )
        conversation = server.store.create_conversation(
            agent_id=agent["id"],
            name="Sherlog",
            conversation_key="research:sherlog",
        )
        run = server.store.create_run(
            agent_id=agent["id"],
            conversation_id=conversation["id"],
            conversation_key="research:sherlog",
            input_markdown="Research sherlog",
            callback_token="secret-callback-token",
            idempotency_key="idem_1",
            request_id="run_1",
        )
        server.store.record_progress(
            request_id="run_1",
            conversation_key="research:sherlog",
            callback_token="secret-callback-token",
            message="Progress with secret-callback-token",
            title="Working",
            payload={"echo": "secret-callback-token"},
        )
        server.store.ask_user(
            request_id="run_1",
            conversation_key="research:sherlog",
            callback_token="secret-callback-token",
            question="Question with secret-callback-token",
            choices=["Continue"],
            context="Context",
        )
        server.store.record_result(
            request_id="run_1",
            conversation_key="research:sherlog",
            callback_token="secret-callback-token",
            status="done",
            title="Done",
            markdown="Final Markdown with secret-callback-token",
            artifacts=[
                {
                    "name": "result.md",
                    "mime_type": "text/markdown",
                    "content": "Artifact with secret-callback-token",
                    "metadata": {"echo": "secret-callback-token"},
                }
            ],
        )
        response = client.get(
            f"/api/runs/{run['id']}",
            headers={"Authorization": "Bearer local-secret"},
        )

    assert response.status_code == 200
    body = response.json()
    rendered = str(body)
    assert body["run"]["status"] == "done"
    assert [event["event_type"] for event in body["events"]] == ["progress", "question", "result"]
    assert body["events"][-1]["title"] == "Done"
    assert "Final Markdown" in body["events"][-1]["markdown"]
    assert body["artifacts"][0]["content"].startswith("Artifact with")
    assert "secret-callback-token" not in rendered
    assert "callback_token_hash" not in rendered
    assert "[redacted-callback-token]" in rendered


def test_run_stream_returns_snapshot_for_terminal_run(tmp_path: Path) -> None:
    import json

    client, _ = _client(tmp_path)

    with client:
        from workspace_agent_relay_mcp import server

        agent = server.store.upsert_agent(
            name="default",
            trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
            token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
        )
        conversation = server.store.create_conversation(
            agent_id=agent["id"],
            name="Sherlog",
            conversation_key="research:sherlog",
        )
        run = server.store.create_run(
            agent_id=agent["id"],
            conversation_id=conversation["id"],
            conversation_key="research:sherlog",
            input_markdown="Research sherlog",
            callback_token="secret-callback-token",
            idempotency_key="idem_stream",
            request_id="run_stream",
        )
        server.store.record_result(
            request_id="run_stream",
            conversation_key="research:sherlog",
            callback_token="secret-callback-token",
            status="done",
            title="Done",
            markdown="Finished",
        )
        response = client.get(f"/api/runs/{run['id']}/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    data_line = next(line for line in response.text.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["run"]["status"] == "done"
    assert payload["events"][-1]["title"] == "Done"
