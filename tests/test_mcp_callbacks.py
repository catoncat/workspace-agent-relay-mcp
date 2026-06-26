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
        "record_progress",
        "record_result",
        "ask_user",
        "get_run_context",
    }
    rendered = str(result)
    assert "auth_token" not in rendered
    assert "default_agent_token" not in rendered
    assert "callback_token" not in rendered
