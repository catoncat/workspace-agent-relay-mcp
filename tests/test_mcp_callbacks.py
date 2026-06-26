import asyncio
from pathlib import Path

from workspace_agent_relay_mcp.db import RelayStore


def _call(tool, *args, **kwargs):
    fn = tool.fn if hasattr(tool, "fn") else tool
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


def _seed_run(store: RelayStore) -> None:
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )


def test_record_result_tool_persists_final_markdown(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    result = _call(
        server.record_result,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        status="done",
        title="Final",
        markdown="Full answer",
        artifacts=[],
    )
    run = store.get_run_by_request_id("run_1")

    assert result["success"] is True
    assert run["status"] == "done"
    assert store.list_events(run["id"])[0]["markdown"] == "Full answer"


def test_record_progress_rejects_wrong_callback_token(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    result = _call(
        server.record_progress,
        request_id="run_1",
        callback_token="wrong",
        conversation_key="research:sherlog",
        message="Working",
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_callback_token"


def test_server_info_lists_relay_tools(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    monkeypatch.setattr(server, "store", RelayStore(tmp_path / "relay.sqlite"))
    result = _call(server.server_info)

    assert result["success"] is True
    assert set(result["tools"]) == {
        "server_info",
        "record_plan",
        "record_progress",
        "record_result",
        "ask_user",
        "get_run_context",
    }
    rendered = str(result)
    assert "auth_token" not in rendered
    assert "default_agent_token" not in rendered
    assert "callback_token" not in rendered


def test_record_plan_and_step_updates_flow(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    plan_result = _call(
        server.record_plan,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        steps=[
            {"id": "s1", "title": "确认改动边界"},
            {"id": "s2", "title": "修复 Header"},
            {"id": "s3", "title": "运行验证"},
        ],
    )
    assert plan_result["success"] is True
    plan = plan_result["plan"]
    assert [step["id"] for step in plan["steps"]] == ["s1", "s2", "s3"]
    assert all(step["status"] == "pending" for step in plan["steps"])

    run = store.get_run_by_request_id("run_1")
    plan_in_detail = store.get_plan(run["id"])
    assert plan_in_detail is not None
    assert len(plan_in_detail["steps"]) == 3

    progress = _call(
        server.record_progress,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        message="完成边界确认，开始修 Header",
        step_updates=[
            {"id": "s1", "status": "done", "note": "边界已确认"},
            {"id": "s2", "status": "in_progress"},
            {"id": "ghost", "status": "done"},
        ],
    )
    assert progress["success"] is True
    updated = progress["plan"]["steps"]
    by_id = {step["id"]: step for step in updated}
    assert by_id["s1"]["status"] == "done"
    assert by_id["s1"]["note"] == "边界已确认"
    assert by_id["s2"]["status"] == "in_progress"
    assert by_id["s3"]["status"] == "pending"

    events = store.list_events(run["id"])
    progress_events = [event for event in events if event["event_type"] == "progress"]
    assert progress_events, "expected a progress event"
    import json as _json

    payload = _json.loads(progress_events[-1]["payload_json"])
    assert payload["ignored_step_ids"] == ["ghost"]
    assert any(update["id"] == "s1" for update in payload["step_updates"])

    run_detail_plan = store.get_plan(run["id"])
    assert run_detail_plan is not None
    assert by_id["s1"]["status"] == "done"


def test_record_plan_rejects_invalid_steps(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    dup = _call(
        server.record_plan,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        steps=[
            {"id": "s1", "title": "A"},
            {"id": "s1", "title": "B"},
        ],
    )
    assert dup["success"] is False
    assert dup["error"]["code"] == "invalid_plan"

    missing_title = _call(
        server.record_plan,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        steps=[{"id": "s1", "title": ""}],
    )
    assert missing_title["success"] is False


def test_record_plan_replaces_existing_plan(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    _call(
        server.record_plan,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        steps=[{"id": "s1", "title": "Old"}],
    )
    replaced = _call(
        server.record_plan,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        steps=[{"id": "a", "title": "New A"}, {"id": "b", "title": "New B"}],
    )
    assert replaced["success"] is True
    assert [step["id"] for step in replaced["plan"]["steps"]] == ["a", "b"]
