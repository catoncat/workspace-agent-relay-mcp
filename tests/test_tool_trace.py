import json
from pathlib import Path

from workspace_agent_relay_mcp.db import RelayStore


def _seed_run(store: RelayStore, *, request_id: str = "run_1") -> dict:
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    conversation = store.create_conversation(
        agent_id=agent["id"],
        name="Sherlog",
        conversation_key="research:sherlog",
    )
    store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key=request_id,
        request_id=request_id,
    )
    return {"agent": agent, "conversation": conversation}


def test_record_tool_trace_validates_callback_token(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)

    wrong = store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="wrong",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
    )

    assert wrong["success"] is False
    assert wrong["error"]["code"] == "invalid_callback_token"
    run = store.get_run_by_request_id("run_1")
    assert store.list_events(run["id"]) == []


def test_record_tool_trace_rejects_conversation_mismatch(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)

    mismatch = store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:other",
        callback_token="secret-callback",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
    )

    assert mismatch["success"] is False
    assert mismatch["error"]["code"] == "conversation_mismatch"


def test_record_tool_trace_rejects_unknown_request_id(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)

    missing = store.record_tool_trace(
        request_id="run_missing",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
    )

    assert missing["success"] is False
    assert missing["error"]["code"] == "run_not_found"


def test_record_tool_trace_rejects_terminal_run(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    trace = store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
    )

    assert trace["success"] is False
    assert trace["error"]["code"] == "run_closed"
    assert store.get_run_by_request_id("run_1")["status"] == "done"


def test_record_tool_trace_appends_progress_event_with_trace_marker(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    run = store.get_run_by_request_id("run_1")

    result = store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
        args_summary={"path": "frontend/src/components/ThreadView.tsx", "hunks": 3},
        result_summary={"files": 1},
        started_at="2026-06-26T12:00:00Z",
        duration_ms=42,
        ok=True,
    )

    assert result["success"] is True
    assert isinstance(result["event_id"], int)
    events = store.list_events(run["id"])
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "progress"
    assert event["title"] == "apply_patch → ThreadView.tsx"
    # markdown is a compact one-line summary
    assert event["markdown"].count("\n") == 0
    assert "✓ apply_patch" in event["markdown"]
    assert "(42ms)" in event["markdown"]
    payload = json.loads(event["payload_json"])
    assert payload["trace"] is True
    assert payload["tool"] == "apply_patch"
    assert payload["args_summary"]["hunks"] == 3
    assert payload["result_summary"] == {"files": 1}
    assert payload["duration_ms"] == 42
    assert payload["ok"] is True
    assert payload["error"] is None
    # trace must not mutate run status (no push to waiting)
    assert store.get_run_by_request_id("run_1")["status"] == "draft"


def test_record_tool_trace_failure_markdown_truncates_error(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    run = store.get_run_by_request_id("run_1")
    long_error = "boom " * 100  # ~500 chars, multi-line-free

    result = store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="run_command",
        title="run_command",
        duration_ms=7,
        ok=False,
        error=long_error,
    )

    assert result["success"] is True
    event = store.list_events(run["id"])[-1]
    assert event["markdown"].count("\n") == 0
    assert "✗ run_command" in event["markdown"]
    assert "(failed:" in event["markdown"]
    assert "…" in event["markdown"]  # error was truncated
    payload = json.loads(event["payload_json"])
    assert payload["ok"] is False
    assert payload["error"] == long_error  # full error preserved in payload


def test_record_tool_trace_does_not_touch_plan_steps(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    run = store.get_run_by_request_id("run_1")
    store.record_plan(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        steps=[{"id": "s1", "title": "Confirm changed files"}],
    )

    store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
    )

    plan = store.get_plan(run["id"])
    assert plan is not None
    assert [step["id"] for step in plan["steps"]] == ["s1"]
    assert all(step["status"] == "pending" for step in plan["steps"])


def test_record_tool_trace_redacts_callback_token_in_payload(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    run = store.get_run_by_request_id("run_1")

    store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="apply_patch",
        title="echo secret-callback",
        args_summary={"secret": "secret-callback"},
        error="failed secret-callback",
        ok=False,
    )

    event = store.list_events(run["id"])[-1]
    rendered = str(event)
    assert "secret-callback" not in rendered
    assert "[redacted-callback-token]" in rendered


def test_record_tool_trace_keeps_existing_progress_tests_working(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    run = store.get_run_by_request_id("run_1")

    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="Reading repository",
        title="Working",
    )
    trace = store.record_tool_trace(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        tool="apply_patch",
        title="apply_patch → ThreadView.tsx",
    )

    assert progress["success"] is True
    assert trace["success"] is True
    events = store.list_events(run["id"])
    assert [event["event_type"] for event in events] == ["progress", "progress"]
    trace_event = events[-1]
    assert json.loads(trace_event["payload_json"])["trace"] is True
    # record_progress still pushes run to waiting; trace does not revert it.
    assert store.get_run_by_request_id("run_1")["status"] == "waiting"


# ---------------------------------------------------------------------------
# HTTP-level tests for POST /internal/tool-trace
# ---------------------------------------------------------------------------


def _http_client(tmp_path: Path, *, auth_token: str = "") -> tuple:
    from starlette.testclient import TestClient

    from workspace_agent_relay_mcp import server
    from workspace_agent_relay_mcp.config import RelayConfig
    from workspace_agent_relay_mcp.db import RelayStore

    server.config = RelayConfig(
        state_dir=tmp_path / "state",
        auth_token=auth_token,
        default_agent_token="agent-token",
        default_trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
    )
    server.store = RelayStore(server.config.database_path)
    app = server.build_http_app()
    return TestClient(app), server.store


def _seed_active_run(store: RelayStore, *, callback_token: str = "secret-callback") -> dict:
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
    )
    conversation = store.create_conversation(
        agent_id=agent["id"],
        name="Sherlog",
        conversation_key="research:sherlog",
    )
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token=callback_token,
        idempotency_key="idem_1",
        request_id="run_1",
    )
    return run


def test_internal_tool_trace_with_correct_token_returns_200_and_creates_event(tmp_path: Path) -> None:
    client, store = _http_client(tmp_path)
    run = _seed_active_run(store)

    with client:
        response = client.post(
            "/internal/tool-trace",
            json={
                "request_id": "run_1",
                "conversation_key": "research:sherlog",
                "callback_token": "secret-callback",
                "tool": "apply_patch",
                "title": "apply_patch → ThreadView.tsx",
                "args_summary": {"path": "frontend/src/components/ThreadView.tsx", "hunks": 3},
                "duration_ms": 42,
                "ok": True,
            },
        )
        detail = client.get(f"/api/runs/{run['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["event_id"], int)
    events = detail.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "progress"
    assert json.loads(events[0]["payload_json"])["trace"] is True


def test_internal_tool_trace_with_wrong_token_returns_401(tmp_path: Path) -> None:
    client, store = _http_client(tmp_path)
    _seed_active_run(store)

    with client:
        response = client.post(
            "/internal/tool-trace",
            json={
                "request_id": "run_1",
                "conversation_key": "research:sherlog",
                "callback_token": "wrong-token",
                "tool": "apply_patch",
                "title": "apply_patch → ThreadView.tsx",
            },
        )

    assert response.status_code == 401
    assert response.json()["success"] is False


def test_internal_tool_trace_with_unknown_request_id_returns_404(tmp_path: Path) -> None:
    client, store = _http_client(tmp_path)
    _seed_active_run(store)

    with client:
        response = client.post(
            "/internal/tool-trace",
            json={
                "request_id": "run_missing",
                "conversation_key": "research:sherlog",
                "callback_token": "secret-callback",
                "tool": "apply_patch",
                "title": "apply_patch → ThreadView.tsx",
            },
        )

    assert response.status_code == 404
    assert response.json()["success"] is False


def test_internal_tool_trace_bypasses_dashboard_bearer_auth(tmp_path: Path) -> None:
    # When a dashboard auth_token is configured, /api/* requires that token,
    # but /internal/tool-trace must NOT — it authenticates via the run's
    # callback_token in the body instead.
    client, store = _http_client(tmp_path, auth_token="local-secret")
    _seed_active_run(store)

    with client:
        response = client.post(
            "/internal/tool-trace",
            json={
                "request_id": "run_1",
                "conversation_key": "research:sherlog",
                "callback_token": "secret-callback",
                "tool": "apply_patch",
                "title": "apply_patch → ThreadView.tsx",
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_internal_tool_trace_rejects_missing_required_fields(tmp_path: Path) -> None:
    client, store = _http_client(tmp_path)
    _seed_active_run(store)

    with client:
        missing_tool = client.post(
            "/internal/tool-trace",
            json={
                "request_id": "run_1",
                "conversation_key": "research:sherlog",
                "callback_token": "secret-callback",
                "title": "apply_patch → ThreadView.tsx",
            },
        )
        malformed = client.post(
            "/internal/tool-trace",
            content="{",
            headers={"Content-Type": "application/json"},
        )

    assert missing_tool.status_code == 400
    assert missing_tool.json()["success"] is False
    assert malformed.status_code == 400
    assert malformed.json() == {"success": False, "error": "malformed JSON body"}
