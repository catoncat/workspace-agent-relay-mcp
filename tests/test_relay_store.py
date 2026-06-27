from pathlib import Path
import hashlib
import json
import threading

import pytest

from workspace_agent_relay_mcp.db import RelayStore


def test_store_creates_default_agent_from_env_config(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
    )

    assert agent["name"] == "default"
    assert agent["trigger_id"] == "agtch_test"
    assert agent["trigger_url"].endswith("/agtch_test/trigger")
    assert agent["token_ref"] == "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN"


def test_store_rename_agent(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
    )
    renamed = store.rename_agent(agent["id"], name="Work")
    assert renamed["name"] == "Work"
    assert store.list_agents()[0]["name"] == "Work"


def test_store_create_agent_stores_local_access_token(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.create_agent(
        name="work",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_work/trigger",
        access_token="at-secret",
    )
    assert agent["token_ref"] == f"local:{agent['id']}"
    assert store.get_agent_access_token(int(agent["id"])) == "at-secret"


def test_store_set_agent_access_token_migrates_to_local_ref(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="legacy",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
    )
    store.set_agent_access_token(int(agent["id"]), access_token="at-new")
    updated = store.get_agent(int(agent["id"]))
    assert updated["token_ref"] == f"local:{agent['id']}"
    assert store.get_agent_access_token(int(agent["id"])) == "at-new"


def test_create_run_hashes_callback_token_and_validates_it(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="hello",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    assert run["request_id"] == "run_1"
    assert "callback_token_hash" not in run
    assert "secret-callback" not in str(run)
    secret_run = store.get_run_by_request_id("run_1", include_secret_hash=True)
    assert secret_run["callback_token_hash"] == hashlib.sha256(b"secret-callback").hexdigest()
    assert "secret-callback" not in str(secret_run)
    assert store.validate_callback("run_1", "research:sherlog", "secret-callback")["success"] is True
    assert store.validate_callback("run_1", "research:sherlog", "wrong")["success"] is False
    assert store.validate_callback("run_1", "other", "secret-callback")["success"] is False


def test_delete_conversation_archives_it_from_lists(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")

    store.delete_conversation(conversation["id"])

    assert store.list_conversations() == []
    with pytest.raises(KeyError):
        store.delete_conversation(conversation["id"])


def test_pin_conversation_sorts_pinned_first(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    older = store.create_conversation(agent_id=agent["id"], name="Older", conversation_key="older")
    newer = store.create_conversation(agent_id=agent["id"], name="Newer", conversation_key="newer")

    store.set_conversation_pinned(older["id"], pinned=True)

    listed = store.list_conversations()
    assert [item["id"] for item in listed] == [older["id"], newer["id"]]
    assert listed[0]["pinned_at"] is not None

    store.set_conversation_pinned(older["id"], pinned=False)
    assert store.get_conversation(older["id"])["pinned_at"] is None


def test_update_conversation_can_rename_and_pin_together(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Old", conversation_key="old")

    updated = store.update_conversation(conversation["id"], name="New", pinned=True)

    assert updated["name"] == "New"
    assert updated["pinned_at"] is not None


def test_delete_agent_cascades_conversations(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.create_agent(
        name="work",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_work/trigger",
        access_token="at-token",
    )
    store.create_conversation(agent_id=agent["id"], name="Thread", conversation_key="work:thread")

    store.delete_agent(agent["id"])

    assert store.list_agents() == []
    assert store.list_conversations() == []


def test_create_run_redacts_callback_token_echo_from_input_markdown(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")

    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="callback_token: secret-callback",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    stored = store.get_run_by_request_id("run_1")
    listed = store.list_runs_for_conversation(conversation["id"])
    context = store.get_run_context("research:sherlog", limit=1)

    for payload in (run, stored, listed, context):
        rendered = str(payload)
        assert "secret-callback" not in rendered
        assert "[redacted-callback-token]" in rendered


def test_record_progress_result_and_question_update_run_state(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
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

    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="Reading repository",
        title="Working",
        payload={"phase": "scan"},
    )
    assert store.get_run_by_request_id("run_1")["status"] == "waiting"

    question = store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        question="Which branch?",
        choices=["main", "dev"],
        context="Need target branch",
    )
    assert store.get_run_by_request_id("run_1")["status"] == "needs_user"

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
        artifacts=[{"name": "result.md", "mime_type": "text/markdown", "content": "Final answer"}],
    )
    run = store.get_run_by_request_id("run_1")
    events = store.list_events(run["id"])
    artifacts = store.list_artifacts(run["id"])

    assert progress["success"] is True
    assert question["success"] is True
    assert result["success"] is True
    assert run["status"] == "done"
    assert [event["event_type"] for event in events] == ["progress", "question", "result"]
    assert artifacts[0]["name"] == "result.md"


def test_get_run_context_redacts_callback_tokens(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")

    for index in range(1, 4):
        request_id = f"run_{index}"
        store.create_run(
            agent_id=agent["id"],
            conversation_id=conversation["id"],
            conversation_key="research:sherlog",
            input_markdown=f"task {index}",
            callback_token="secret-callback",
            idempotency_key=request_id,
            request_id=request_id,
        )
        store.record_result(
            request_id=request_id,
            conversation_key="research:sherlog",
            callback_token="secret-callback",
            status="done",
            title=f"Finished {index}",
            markdown=f"Final answer {index}",
        )

    context = store.get_run_context("research:sherlog", limit=2)

    rendered = str(context)
    assert context["success"] is True
    assert "secret-callback" not in rendered
    assert "callback_token_hash" not in rendered
    assert [run["request_id"] for run in context["runs"]] == ["run_3", "run_2"]
    assert "run_1" not in rendered


def test_callback_token_echoes_are_redacted_from_callback_content(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="progress message secret-callback",
        title="progress title secret-callback",
        payload={
            "secret-callback-key": "payload value secret-callback",
            "nested": ["list value secret-callback", {"inner": "dict value secret-callback"}],
        },
    )
    store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        question="question secret-callback",
        choices=["choice secret-callback"],
        context="context secret-callback",
    )
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="result title secret-callback",
        markdown="result markdown secret-callback",
        artifacts=[
            {
                "name": "artifact secret-callback",
                "mime_type": "text/secret-callback",
                "content": "artifact content secret-callback",
                "metadata": {
                    "metadata-secret-callback": "metadata value secret-callback",
                    "nested": ["metadata list secret-callback"],
                },
            }
        ],
    )

    events_rendered = str(store.list_events(run["id"]))
    artifacts_rendered = str(store.list_artifacts(run["id"]))
    context_rendered = str(store.get_run_context("research:sherlog", limit=1))

    for rendered in (events_rendered, artifacts_rendered, context_rendered):
        assert "secret-callback" not in rendered
        assert "[redacted-callback-token]" in rendered


def test_artifact_bytes_scalars_are_redacted_after_string_coercion(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
        artifacts=[
            {
                "name": b"name secret-callback",
                "mime_type": b"text/secret-callback",
                "content": b"content secret-callback",
            }
        ],
    )

    artifacts = store.list_artifacts(run["id"])
    rendered = str(artifacts)

    assert result["success"] is True
    assert "secret-callback" not in rendered
    assert "[redacted-callback-token]" in rendered
    assert "[redacted-callback-token]" in artifacts[0]["name"]
    assert "[redacted-callback-token]" in artifacts[0]["mime_type"]
    assert "[redacted-callback-token]" in artifacts[0]["content"]


def test_record_result_rolls_back_result_event_when_artifact_metadata_fails(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    with pytest.raises(TypeError):
        store.record_result(
            request_id="run_1",
            conversation_key="research:sherlog",
            callback_token="secret-callback",
            status="done",
            title="Finished",
            markdown="Final answer",
            artifacts=[
                {
                    "name": "bad.md",
                    "mime_type": "text/markdown",
                    "content": "Final answer",
                    "metadata": {"not_json": object()},
                }
            ],
        )

    assert store.get_run_by_request_id("run_1")["status"] == "draft"
    assert store.list_events(run["id"]) == []


def test_terminal_run_rejects_later_callbacks_without_reopening(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
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
    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="Reading repository",
    )
    question = store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        question="Which branch?",
    )
    second_result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished again",
        markdown="Second answer",
    )

    assert result["success"] is True
    assert progress["success"] is False
    assert progress["error"]["code"] == "run_closed"
    assert question["success"] is False
    assert question["error"]["code"] == "run_closed"
    assert second_result["success"] is False
    assert second_result["error"]["code"] == "run_closed"
    assert store.get_run_by_request_id("run_1")["status"] == "done"


def test_dismiss_run_marks_non_terminal_run_done(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )
    store.update_run_trigger_result(
        request_id="run_1",
        trigger_http_status=202,
        trigger_x_request_id="req_1",
        conversation_url="https://chatgpt.com/c/test",
    )
    store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="Still working",
    )

    dismissed = store.dismiss_run(int(run["id"]), note="Operator confirmed done in ChatGPT")

    assert dismissed["status"] == "done"
    assert dismissed["completed_at"] is not None
    events = store.list_events(int(run["id"]))
    assert events[-1]["event_type"] == "system"
    assert events[-1]["title"] == "Marked finished"
    assert events[-1]["markdown"] == "Operator confirmed done in ChatGPT"
    assert events[-1]["payload_json"] == '{"reason": "operator_dismiss"}'

    late = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Late",
        markdown="Too late",
    )
    assert late["success"] is False
    assert late["error"]["code"] == "run_closed"


def test_dismiss_run_rejects_terminal_run(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    with pytest.raises(ValueError, match="already terminal"):
        store.dismiss_run(int(run["id"]))


def test_terminal_run_checks_callback_token_before_closed_status(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
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
    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    wrong_progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="wrong-callback",
        message="Reading repository",
    )
    wrong_result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="wrong-callback",
        status="done",
        title="Finished again",
        markdown="Second answer",
    )
    correct_progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="Reading repository",
    )
    correct_result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished again",
        markdown="Second answer",
    )

    assert result["success"] is True
    assert wrong_progress["success"] is False
    assert wrong_progress["error"]["code"] == "invalid_callback_token"
    assert wrong_result["success"] is False
    assert wrong_result["error"]["code"] == "invalid_callback_token"
    assert correct_progress["success"] is False
    assert correct_progress["error"]["code"] == "run_closed"
    assert correct_result["success"] is False
    assert correct_result["error"]["code"] == "run_closed"
    assert store.get_run_by_request_id("run_1")["status"] == "done"


def test_late_trigger_result_does_not_reopen_terminal_run(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
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
    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    trigger_update = store.update_run_trigger_result(
        request_id="run_1",
        trigger_http_status=202,
        trigger_x_request_id="trigger_req_1",
        conversation_url="https://chatgpt.com/c/test",
    )
    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        message="Reading repository",
    )

    assert result["success"] is True
    assert trigger_update["status"] == "done"
    assert trigger_update["trigger_status"] == "accepted"
    assert trigger_update["trigger_http_status"] == 202
    assert trigger_update["trigger_x_request_id"] == "trigger_req_1"
    assert trigger_update["conversation_url"] == "https://chatgpt.com/c/test"
    assert progress["success"] is False
    assert progress["error"]["code"] == "run_closed"
    assert store.get_run_by_request_id("run_1")["status"] == "done"


def test_update_run_trigger_result_persists_trigger_error(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_err",
        request_id="run_err",
    )

    failed = store.update_run_trigger_result(
        request_id="run_err",
        trigger_http_status=0,
        trigger_x_request_id=None,
        conversation_url=None,
        trigger_error="TimeoutError: The read operation timed out",
    )

    assert failed["status"] == "trigger_failed"
    assert failed["trigger_error"] == "TimeoutError: The read operation timed out"
    # The column survives a reload (migration path works on existing DBs).
    reloaded = store.get_run_by_request_id("run_err")
    assert reloaded["trigger_error"] == "TimeoutError: The read operation timed out"

    # A subsequent accepted trigger clears the error.
    accepted = store.update_run_trigger_result(
        request_id="run_err",
        trigger_http_status=202,
        trigger_x_request_id="req_ok",
        conversation_url="https://chatgpt.com/c/test",
        trigger_error=None,
    )
    assert accepted["trigger_error"] is None


def test_existing_database_gets_trigger_error_column_via_migration(tmp_path: Path) -> None:
    # Build a runs table WITHOUT the trigger_error column, then confirm the
    # store adds it on init (forward-only migration for existing databases).
    import sqlite3
    db = tmp_path / "relay.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            trigger_url TEXT NOT NULL, trigger_id TEXT NOT NULL, token_ref TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            name TEXT NOT NULL, conversation_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT
        );
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE,
            agent_id INTEGER NOT NULL, conversation_id INTEGER NOT NULL,
            conversation_key TEXT NOT NULL, callback_token_hash TEXT NOT NULL,
            idempotency_key TEXT NOT NULL, input_markdown TEXT NOT NULL,
            trigger_status TEXT NOT NULL DEFAULT 'draft', trigger_http_status INTEGER,
            trigger_x_request_id TEXT, conversation_url TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
            request_id TEXT NOT NULL, event_type TEXT NOT NULL, title TEXT,
            markdown TEXT, payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL,
            name TEXT NOT NULL, mime_type TEXT NOT NULL, content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        );
        """
    )
    conn.close()

    store = RelayStore(db)
    # Opening the store runs _init_schema, which must add the missing column.
    import sqlite3 as _sqlite3
    check = _sqlite3.connect(db)
    cols = {row[1] for row in check.execute("PRAGMA table_info(runs)")}
    check.close()
    for column in ("trigger_error", "parent_run_id", "superseded_by_run_id", "supersede_reason"):
        assert column in cols


def test_record_result_invalid_status_does_not_append_events(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="weird",
        title="Finished",
        markdown="Final answer",
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_status"
    assert store.list_events(run["id"]) == []


def test_record_result_rejects_superseded_status(tmp_path: Path) -> None:
    """`superseded` is system-only (set when a newer turn starts). Agents must not
    be able to set it via record_result. See 2026-06-27-relay-turn-plan-semantics.md."""
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        status="superseded",
        title="Replaced",
        markdown="should not be stored",
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_status"
    assert store.list_events(run["id"]) == []


def test_create_run_supersedes_older_active_runs(tmp_path: Path) -> None:
    """Starting a new turn closes out older non-terminal runs in the same
    conversation: they become `superseded` (terminal), emit a system event, and
    their late callbacks are rejected as run_closed."""
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")

    first = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="first turn",
        callback_token="secret-first",
        idempotency_key="run_1",
        request_id="run_1",
    )
    # Give the first run a plan so we can confirm it freezes rather than vanishes.
    store.record_plan(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-first",
        steps=[{"id": "s1", "title": "Old direction"}],
    )
    # Advance first run to an active, non-terminal status (mimics trigger accepted).
    store.update_run_trigger_result(
        request_id="run_1",
        trigger_http_status=202,
        trigger_x_request_id="req_api_1",
        conversation_url="https://chatgpt.com/c/1",
    )
    assert store.get_run_by_request_id("run_1")["status"] == "accepted"

    second = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="correcting direction",
        callback_token="secret-second",
        idempotency_key="run_2",
        request_id="run_2",
    )

    first_after = store.get_run_by_request_id("run_1")
    assert first_after["status"] == "superseded"
    assert first_after["completed_at"] is not None
    assert first_after["superseded_by_run_id"] == second["id"]
    assert first_after["supersede_reason"] == "follow_up_started"
    assert store.get_run_by_request_id("run_2")["status"] == "draft"
    assert first["parent_run_id"] is None
    assert second["parent_run_id"] == first["id"]

    # A system event explains the supersede.
    events = store.list_events(first["id"])
    system_events = [e for e in events if e["event_type"] == "system"]
    assert len(system_events) == 1
    assert "Superseded" in (system_events[0]["title"] or "")
    system_payload = json.loads(system_events[0]["payload_json"])
    assert system_payload["reason"] == "follow_up_started"
    assert system_payload["superseded_by_run_id"] == second["id"]
    assert system_payload["superseded_by_request_id"] == "run_2"

    # The first run's plan is still readable (frozen snapshot, not deleted).
    assert store.get_plan(first["id"]) is not None

    # Late callback to the superseded run is rejected as run_closed.
    late = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-first",
        message="late",
    )
    assert late["success"] is False
    assert late["error"]["code"] == "run_closed"

    # Already-terminal runs are NOT touched by a third turn.
    store.record_result(
        request_id="run_2",
        conversation_key="research:sherlog",
        callback_token="secret-second",
        status="done",
        title="Done",
        markdown="final",
    )
    third = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="third turn",
        callback_token="secret-third",
        idempotency_key="run_3",
        request_id="run_3",
    )
    # run_2 was already terminal (done); it must not flip to superseded.
    assert store.get_run_by_request_id("run_2")["status"] == "done"
    assert third["status"] == "draft"
    assert third["parent_run_id"] is None


def test_create_run_rejects_mismatched_conversation_id_and_key(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    first_conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    second_conversation = store.create_conversation(agent_id=agent["id"], name="Review", conversation_key="research:review")

    with pytest.raises(ValueError):
        store.create_run(
            agent_id=agent["id"],
            conversation_id=first_conversation["id"],
            conversation_key=second_conversation["conversation_key"],
            input_markdown="task",
            callback_token="secret-callback",
            idempotency_key="run_1",
            request_id="run_1",
        )

    with pytest.raises(KeyError):
        store.get_run_by_request_id("run_1")


def test_create_run_rejects_agent_that_does_not_own_conversation(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    owning_agent = store.upsert_agent(
        name="owner",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_owner/trigger",
        token_ref="env:OWNER_TOKEN",
    )
    other_agent = store.upsert_agent(
        name="other",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_other/trigger",
        token_ref="env:OTHER_TOKEN",
    )
    conversation = store.create_conversation(
        agent_id=owning_agent["id"],
        name="Sherlog",
        conversation_key="research:sherlog",
    )

    with pytest.raises(ValueError):
        store.create_run(
            agent_id=other_agent["id"],
            conversation_id=conversation["id"],
            conversation_key=conversation["conversation_key"],
            input_markdown="task",
            callback_token="secret-callback",
            idempotency_key="run_1",
            request_id="run_1",
        )

    assert store.list_runs_for_conversation(conversation["id"]) == []
    with pytest.raises(KeyError):
        store.get_run_by_request_id("run_1")


def test_concurrent_store_instances_cannot_reopen_terminal_run_with_stale_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "relay.sqlite"
    setup_store = RelayStore(database_path)
    progress_store = RelayStore(database_path)
    result_store = RelayStore(database_path)
    agent = setup_store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = setup_store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    setup_store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )

    progress_validated = threading.Event()
    release_progress = threading.Event()
    result_entered_validation = threading.Event()
    result_finished = threading.Event()
    progress_result: dict[str, object] = {}
    result_result: dict[str, object] = {}
    progress_errors: list[BaseException] = []
    result_errors: list[BaseException] = []

    original_progress_validate = progress_store._validate_callback_conn
    original_result_validate = result_store._validate_callback_conn

    def pause_after_progress_validation(*args: object, **kwargs: object) -> dict[str, object]:
        validation = original_progress_validate(*args, **kwargs)
        progress_validated.set()
        if not release_progress.wait(timeout=2):
            raise TimeoutError("progress callback was not released")
        return validation

    def mark_result_validation(*args: object, **kwargs: object) -> dict[str, object]:
        result_entered_validation.set()
        return original_result_validate(*args, **kwargs)

    monkeypatch.setattr(progress_store, "_validate_callback_conn", pause_after_progress_validation)
    monkeypatch.setattr(result_store, "_validate_callback_conn", mark_result_validation)

    def record_progress() -> None:
        try:
            progress_result["value"] = progress_store.record_progress(
                request_id="run_1",
                conversation_key="research:sherlog",
                callback_token="secret-callback",
                message="Reading repository",
            )
        except BaseException as exc:
            progress_errors.append(exc)

    def record_result() -> None:
        try:
            result_result["value"] = result_store.record_result(
                request_id="run_1",
                conversation_key="research:sherlog",
                callback_token="secret-callback",
                status="done",
                title="Finished",
                markdown="Final answer",
            )
        except BaseException as exc:
            result_errors.append(exc)
        finally:
            result_finished.set()

    progress_thread = threading.Thread(target=record_progress)
    result_thread = threading.Thread(target=record_result)
    progress_thread.start()
    try:
        assert progress_validated.wait(timeout=2)
        result_thread.start()
        assert result_entered_validation.wait(timeout=0.25) is False
    finally:
        release_progress.set()
        progress_thread.join(timeout=2)
        if result_thread.ident is not None:
            result_thread.join(timeout=2)

    assert not progress_thread.is_alive()
    assert not result_thread.is_alive()
    assert result_finished.wait(timeout=0)
    assert progress_errors == []
    assert result_errors == []
    assert progress_result["value"]["success"] is True
    assert result_result["value"]["success"] is True
    run = setup_store.get_run_by_request_id("run_1")
    events = setup_store.list_events(run["id"])
    assert run["status"] == "done"
    assert [event["event_type"] for event in events] == ["progress", "result"]
