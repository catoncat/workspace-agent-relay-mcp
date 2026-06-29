from pathlib import Path
import json
import sqlite3
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


def test_create_run_validates_callbacks_by_request_id_and_conversation_key(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="hello",
        idempotency_key="run_1",
        request_id="run_1",
    )

    assert run["request_id"] == "run_1"
    assert "callback_token_hash" not in run
    # No callback_token is stored anywhere on the run row.
    assert "callback_token" not in run
    # record_progress routes by request_id + conversation_key; a mismatched
    # conversation_key is rejected (this is the real cross-conversation guard).
    assert store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="ok",
    )["success"] is True
    assert store.record_progress(
        request_id="run_1",
        conversation_key="other",
        message="wrong conversation",
    )["error"]["code"] == "conversation_mismatch"
    assert store.record_progress(
        request_id="missing",
        conversation_key="research:sherlog",
        message="unknown run",
    )["error"]["code"] == "run_not_found"


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


def test_app_settings_current_agent_falls_back_and_delete_updates(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    first = store.create_agent(
        name="first",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_first/trigger",
        access_token="at-first",
    )
    second = store.create_agent(
        name="second",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_second/trigger",
        access_token="at-second",
    )

    assert store.get_settings()["current_agent_id"] == first["id"]

    updated = store.update_settings(current_agent_id=second["id"])
    assert updated["current_agent_id"] == second["id"]

    store.delete_agent(second["id"])
    assert store.get_settings()["current_agent_id"] == first["id"]

    store.delete_agent(first["id"])
    assert store.get_settings()["current_agent_id"] is None


def test_workspace_crud_and_run_working_directory_snapshot(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    workspace_dir = tmp_path / "repo"
    workspace_dir.mkdir()
    next_dir = tmp_path / "repo-renamed"
    next_dir.mkdir()

    workspace = store.create_workspace(name="Relay", working_directory=str(workspace_dir))
    assert workspace["name"] == "Relay"
    assert workspace["working_directory"] == str(workspace_dir)
    assert store.list_workspaces()[0]["id"] == workspace["id"]

    store.update_settings(current_workspace_id=workspace["id"])
    conversation = store.create_conversation(
        agent_id=agent["id"],
        workspace_id=store.get_settings()["current_workspace_id"],
        name="Relay thread",
        conversation_key="repo:relay",
    )
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="repo:relay",
        input_markdown="hello",
        idempotency_key="run_1",
        request_id="run_1",
    )

    assert conversation["workspace_id"] == workspace["id"]
    assert run["workspace_id"] == workspace["id"]
    assert run["working_directory_snapshot"] == str(workspace_dir)

    updated = store.update_workspace(
        workspace["id"],
        name="Relay renamed",
        working_directory=str(next_dir),
    )
    assert updated["name"] == "Relay renamed"
    assert updated["working_directory"] == str(next_dir)
    assert store.get_run(run["id"])["working_directory_snapshot"] == str(workspace_dir)

    store.delete_workspace(workspace["id"])

    assert store.get_settings()["current_workspace_id"] is None
    assert store.get_conversation(conversation["id"])["workspace_id"] is None
    assert store.get_run(run["id"])["workspace_id"] == workspace["id"]
    assert store.get_run(run["id"])["working_directory_snapshot"] == str(workspace_dir)


def test_legacy_database_migration_sets_workspace_fields_to_null(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                trigger_url TEXT NOT NULL,
                trigger_id TEXT NOT NULL,
                token_ref TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                conversation_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT,
                pinned_at TEXT
            );
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                conversation_key TEXT NOT NULL,
                parent_run_id INTEGER,
                superseded_by_run_id INTEGER,
                supersede_reason TEXT,
                trigger_error TEXT,
                idempotency_key TEXT NOT NULL,
                input_markdown TEXT NOT NULL,
                trigger_status TEXT NOT NULL DEFAULT 'draft',
                trigger_http_status INTEGER,
                trigger_x_request_id TEXT,
                conversation_url TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            INSERT INTO agents (id, name, trigger_url, trigger_id, token_ref, created_at, updated_at)
            VALUES (1, 'default', 'https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger', 'agtch_test', 'env:TOKEN', 'now', 'now');
            INSERT INTO conversations (id, agent_id, name, conversation_key, created_at, updated_at)
            VALUES (1, 1, 'Legacy', 'legacy:key', 'now', 'now');
            INSERT INTO runs (
                id, request_id, agent_id, conversation_id, conversation_key,
                idempotency_key, input_markdown, created_at, updated_at
            )
            VALUES (1, 'run_1', 1, 1, 'legacy:key', 'idem_1', 'hello', 'now', 'now');
            """
        )

    store = RelayStore(db_path)

    assert store.get_conversation(1)["workspace_id"] is None
    run = store.get_run(1)
    assert run["workspace_id"] is None
    assert run["working_directory_snapshot"] is None


def test_create_run_stores_input_markdown_verbatim(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")

    store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="just some user text",
        idempotency_key="run_1",
        request_id="run_1",
    )

    stored = store.get_run_by_request_id("run_1")
    listed = store.list_runs_for_conversation(conversation["id"])
    context = store.get_run_context("research:sherlog", limit=1)

    assert stored["input_markdown"] == "just some user text"
    assert listed[0]["input_markdown"] == "just some user text"
    assert "just some user text" in str(context)


def test_record_progress_result_and_question_update_run_state(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )

    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="Reading repository",
        title="Working",
        payload={"phase": "scan"},
    )
    assert store.get_run_by_request_id("run_1")["status"] == "waiting"

    question = store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        question="Which branch?",
        choices=["main", "dev"],
        context="Need target branch",
    )
    assert store.get_run_by_request_id("run_1")["status"] == "needs_user"

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
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


def test_get_run_context_returns_capped_recent_runs(tmp_path: Path) -> None:
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
            idempotency_key=request_id,
            request_id=request_id,
        )
        store.record_result(
            request_id=request_id,
            conversation_key="research:sherlog",
            status="done",
            title=f"Finished {index}",
            markdown=f"Final answer {index}",
        )

    context = store.get_run_context("research:sherlog", limit=2)

    rendered = str(context)
    assert context["success"] is True
    assert "callback_token_hash" not in rendered
    assert "callback_token" not in rendered
    assert [run["request_id"] for run in context["runs"]] == ["run_3", "run_2"]
    assert "run_1" not in rendered


def test_record_progress_result_and_question_keep_content_verbatim(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )

    store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="progress message",
        title="progress title",
        payload={"phase": "scan"},
    )
    store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        question="which branch?",
        choices=["main"],
        context="need target",
    )
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="result title",
        markdown="result markdown",
        artifacts=[
            {
                "name": "artifact.md",
                "mime_type": "text/markdown",
                "content": "artifact content",
                "metadata": {"k": "v", "nested": ["list value"]},
            }
        ],
    )

    events = store.list_events(run["id"])
    artifacts = store.list_artifacts(run["id"])
    events_rendered = str(events)
    artifacts_rendered = str(artifacts)

    assert "progress message" in events_rendered
    assert "progress title" in events_rendered
    assert "which branch?" in events_rendered
    assert "result markdown" in events_rendered
    assert artifacts[0]["name"] == "artifact.md"
    assert artifacts[0]["content"] == "artifact content"
    assert "list value" in artifacts_rendered


def test_record_result_coerces_bytes_artifact_scalars_to_str(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Finished",
        markdown="Final answer",
        artifacts=[
            {
                "name": b"name-bytes",
                "mime_type": b"text/markdown",
                "content": b"content-bytes",
            }
        ],
    )

    artifacts = store.list_artifacts(run["id"])

    assert result["success"] is True
    # Bytes scalars are coerced via str(), which renders the b'...' repr
    # (same as the pre-removal behavior — no special bytes decoding).
    assert artifacts[0]["name"] == str(b"name-bytes")
    assert artifacts[0]["mime_type"] == str(b"text/markdown")
    assert artifacts[0]["content"] == str(b"content-bytes")


def test_record_result_rolls_back_result_event_when_artifact_metadata_fails(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )

    with pytest.raises(TypeError):
        store.record_result(
            request_id="run_1",
            conversation_key="research:sherlog",
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
        idempotency_key="run_1",
        request_id="run_1",
    )
    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="Reading repository",
    )
    question = store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        question="Which branch?",
    )
    second_result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
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
        idempotency_key="run_1",
        request_id="run_1",
    )
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    with pytest.raises(ValueError, match="already terminal"):
        store.dismiss_run(int(run["id"]))


def test_terminal_run_rejects_callbacks_and_mismatched_conversation(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )
    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Finished",
        markdown="Final answer",
    )

    # Same conversation on a terminal run -> run_closed (the turn is sealed).
    late_progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="Reading repository",
    )
    late_result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Finished again",
        markdown="Second answer",
    )
    # Wrong conversation_key is rejected (cross-conversation guard) — and the
    # mismatch is checked before the terminal-status check, so it surfaces as
    # conversation_mismatch even on a closed run.
    mismatched = store.record_progress(
        request_id="run_1",
        conversation_key="other",
        message="wrong conversation",
    )

    assert result["success"] is True
    assert late_progress["success"] is False
    assert late_progress["error"]["code"] == "run_closed"
    assert late_result["success"] is False
    assert late_result["error"]["code"] == "run_closed"
    assert mismatched["success"] is False
    assert mismatched["error"]["code"] == "conversation_mismatch"
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
        idempotency_key="run_1",
        request_id="run_1",
    )
    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
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
    # Opening the store runs _init_schema, which must add the missing column
    # and drop the legacy callback_token_hash via a table rebuild.
    import sqlite3 as _sqlite3
    check = _sqlite3.connect(db)
    cols = {row[1] for row in check.execute("PRAGMA table_info(runs)")}
    check.close()
    for column in ("trigger_error", "parent_run_id", "superseded_by_run_id", "supersede_reason"):
        assert column in cols
    assert "callback_token_hash" not in cols


def test_existing_database_drops_callback_token_hash_and_preserves_runs(tmp_path: Path) -> None:
    # Build an old-style runs table WITH callback_token_hash and a real row,
    # then confirm the rebuild migration drops the column and keeps the data.
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
        INSERT INTO agents (id, name, trigger_url, trigger_id, token_ref, created_at, updated_at)
            VALUES (1, 'default', 'https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger', 'agtch_test', 'env:TOKEN', '2026-06-28T00:00:00Z', '2026-06-28T00:00:00Z');
        INSERT INTO conversations (id, agent_id, name, conversation_key, created_at, updated_at)
            VALUES (1, 1, 'Sherlog', 'research:sherlog', '2026-06-28T00:00:00Z', '2026-06-28T00:00:00Z');
        INSERT INTO runs (id, request_id, agent_id, conversation_id, conversation_key, callback_token_hash, idempotency_key, input_markdown, trigger_status, status, created_at, updated_at)
            VALUES (1, 'run_1', 1, 1, 'research:sherlog', 'legacy-hash', 'run_1', 'old task', 'accepted', 'accepted', '2026-06-28T00:00:00Z', '2026-06-28T00:00:00Z');
        INSERT INTO events (id, run_id, request_id, event_type, title, markdown, payload_json, created_at)
            VALUES (1, 1, 'run_1', 'progress', 'Working', 'old progress', '{}', '2026-06-28T00:00:00Z');
        """
    )
    conn.commit()
    conn.close()

    store = RelayStore(db)

    # The legacy column is gone; the run row and its event survived the rebuild.
    check = sqlite3.connect(db)
    cols = {row[1] for row in check.execute("PRAGMA table_info(runs)")}
    event_count = check.execute("SELECT COUNT(*) FROM events WHERE run_id = 1").fetchone()[0]
    check.close()
    assert "callback_token_hash" not in cols
    assert event_count == 1

    run = store.get_run_by_request_id("run_1")
    assert run["input_markdown"] == "old task"
    assert run["status"] == "accepted"


def test_record_result_invalid_status_does_not_append_events(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="weird",
        title="Finished",
        markdown="Final answer",
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_status"
    assert store.list_events(run["id"]) == []


def test_record_result_rejects_superseded_status(tmp_path: Path) -> None:
    """`superseded` is system-only. Agents must not set it via record_result."""
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="superseded",
        title="Replaced",
        markdown="should not be stored",
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_status"
    assert store.list_events(run["id"]) == []


def test_create_run_keeps_older_active_runs_open(tmp_path: Path) -> None:
    """Starting a new queued turn does not close older non-terminal runs.

    Queue/new-request sends have their own request_id and must not poison the
    current run: late callbacks for the older request still land on the older
    run until that run records its own result.
    """
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")

    first = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="first turn",
        idempotency_key="run_1",
        request_id="run_1",
    )
    # Give the first run a plan so we can confirm it freezes rather than vanishes.
    store.record_plan(
        request_id="run_1",
        conversation_key="research:sherlog",
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
        idempotency_key="run_2",
        request_id="run_2",
    )

    first_after = store.get_run_by_request_id("run_1")
    assert first_after["status"] == "accepted"
    assert first_after["completed_at"] is None
    assert first_after["superseded_by_run_id"] is None
    assert first_after["supersede_reason"] is None
    assert store.get_run_by_request_id("run_2")["status"] == "draft"
    assert first["parent_run_id"] is None
    assert second["parent_run_id"] == first["id"]

    # No system event closes the older run; queue/new request is distinct from
    # steer and from explicit replacement.
    events = store.list_events(first["id"])
    system_events = [e for e in events if e["event_type"] == "system"]
    assert system_events == []

    # The first run's plan is still readable (frozen snapshot, not deleted).
    assert store.get_plan(first["id"]) is not None

    # Late callback to the still-active older run is accepted.
    late = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="late",
    )
    assert late["success"] is True

    # Already-terminal runs are not touched by a third turn.
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="First done",
        markdown="first final",
    )
    store.record_result(
        request_id="run_2",
        conversation_key="research:sherlog",
        status="done",
        title="Done",
        markdown="final",
    )
    third = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="third turn",
        idempotency_key="run_3",
        request_id="run_3",
    )
    # run_2 was already terminal (done); it must stay done.
    assert store.get_run_by_request_id("run_1")["status"] == "done"
    assert store.get_run_by_request_id("run_2")["status"] == "done"
    assert third["status"] == "draft"
    assert third["parent_run_id"] is None


def _make_active_run(store: RelayStore, *, request_id: str) -> dict:
    """Create a run, give it a plan, and advance it to `accepted` (active)."""
    agent = store.list_agents()[0]
    conversation = store.list_conversations()[0]
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key=conversation["conversation_key"],
        input_markdown="first turn",
        idempotency_key=request_id,
        request_id=request_id,
    )
    store.record_plan(
        request_id=request_id,
        conversation_key=conversation["conversation_key"],
        steps=[{"id": "s1", "title": "Do the thing"}],
    )
    store.update_run_trigger_result(
        request_id=request_id,
        trigger_http_status=202,
        trigger_x_request_id="req_api",
        conversation_url="https://chatgpt.com/c/1",
    )
    return run


def test_steer_run_appends_user_message_on_same_run(tmp_path: Path) -> None:
    """Steer appends a user_message event on the SAME run (same request_id).
    No credential rotation is involved; callbacks still route by request_id."""
    store = RelayStore(tmp_path / "relay.sqlite")
    store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    store.create_conversation(agent_id=store.list_agents()[0]["id"], name="Sherlog", conversation_key="research:sherlog")
    _make_active_run(store, request_id="run_1")
    assert store.get_run_by_request_id("run_1")["status"] == "accepted"

    steered = store.steer_run(
        run_id=store.get_run_by_request_id("run_1")["id"],
        user_input="You didn't push.",
    )

    # Same turn identity (request_id preserved); still active.
    assert steered["request_id"] == "run_1"
    assert steered["status"] == "accepted"
    # No new run row was created.
    assert len(store.list_runs_for_conversation(store.list_conversations()[0]["id"])) == 1

    # A user_message event was appended on the same run.
    events = store.list_events(steered["id"])
    user_messages = [e for e in events if e["event_type"] == "user_message"]
    assert len(user_messages) == 1
    assert user_messages[0]["markdown"] == "You didn't push."
    assert json.loads(user_messages[0]["payload_json"])["source"] == "operator_steer"

    # Callbacks still work after steer (no token to rotate).
    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="progress after steer",
        step_updates=[{"id": "s1", "status": "in_progress"}],
    )
    assert progress["success"] is True


def test_steer_run_rejects_terminal_or_missing_run(tmp_path: Path) -> None:
    """Steer is only for active runs: terminal runs raise ValueError (the
    operator should send a new turn), missing runs raise KeyError."""
    store = RelayStore(tmp_path / "relay.sqlite")
    store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    store.create_conversation(agent_id=store.list_agents()[0]["id"], name="Sherlog", conversation_key="research:sherlog")
    run = _make_active_run(store, request_id="run_1")
    # Finish the run -> terminal.
    store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Done",
        markdown="final",
    )
    assert store.get_run_by_request_id("run_1")["status"] == "done"

    with pytest.raises(ValueError):
        store.steer_run(run_id=run["id"], user_input="too late")

    with pytest.raises(KeyError):
        store.steer_run(run_id=999999, user_input="no run")


def test_steer_lets_agent_finish_same_turn(tmp_path: Path) -> None:
    """After steer, the agent can record_result(done) on the SAME request_id
    to close the turn. No token rotation is involved."""
    store = RelayStore(tmp_path / "relay.sqlite")
    store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    store.create_conversation(agent_id=store.list_agents()[0]["id"], name="Sherlog", conversation_key="research:sherlog")
    _make_active_run(store, request_id="run_1")
    store.steer_run(
        run_id=store.get_run_by_request_id("run_1")["id"],
        user_input="You didn't push.",
    )

    result = store.record_result(
        request_id="run_1",
        conversation_key="research:sherlog",
        status="done",
        title="Done",
        markdown="pushed and finished",
    )
    assert result["success"] is True
    assert store.get_run_by_request_id("run_1")["status"] == "done"


def test_steer_run_on_needs_user_resumes_turn(tmp_path: Path) -> None:
    """Steering a run that is paused on ask_user (needs_user) is the operator's
    ANSWER: it appends a user_message and transitions the run OUT of the
    question state to "sent" (the trigger-result update in the route then
    advances it to "accepted"). request_id is preserved (same turn), no new
    run row is created, and callbacks resume on the same request_id."""
    store = RelayStore(tmp_path / "relay.sqlite")
    store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    store.create_conversation(agent_id=store.list_agents()[0]["id"], name="Sherlog", conversation_key="research:sherlog")
    _make_active_run(store, request_id="run_1")
    # Agent pauses on a human decision -> run is needs_user.
    store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        question="Which branch should I target?",
        choices=["main", "dev"],
    )
    assert store.get_run_by_request_id("run_1")["status"] == "needs_user"

    steered = store.steer_run(
        run_id=store.get_run_by_request_id("run_1")["id"],
        user_input="Target the dev branch.",
    )

    # Same turn identity (request_id preserved); the question state is left.
    assert steered["request_id"] == "run_1"
    assert steered["status"] == "sent"
    # No new run row was created.
    assert len(store.list_runs_for_conversation(store.list_conversations()[0]["id"])) == 1

    # A user_message event was appended on the same run.
    events = store.list_events(steered["id"])
    user_messages = [e for e in events if e["event_type"] == "user_message"]
    assert len(user_messages) == 1
    assert user_messages[0]["markdown"] == "Target the dev branch."
    assert json.loads(user_messages[0]["payload_json"])["source"] == "operator_steer"

    # The agent resumes the turn on the same request_id (no token to rotate).
    progress = store.record_progress(
        request_id="run_1",
        conversation_key="research:sherlog",
        message="resuming with the answer",
        step_updates=[{"id": "s1", "status": "in_progress"}],
    )
    assert progress["success"] is True


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
            idempotency_key="run_1",
            request_id="run_1",
        )

    assert store.list_runs_for_conversation(conversation["id"]) == []
    with pytest.raises(KeyError):
        store.get_run_by_request_id("run_1")


def test_concurrent_store_instances_serialize_callbacks_via_store_lock(
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
                message="Reading repository",
            )
        except BaseException as exc:
            progress_errors.append(exc)

    def record_result() -> None:
        try:
            result_result["value"] = result_store.record_result(
                request_id="run_1",
                conversation_key="research:sherlog",
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


def test_new_schema_excludes_retired_polling_and_pull_columns(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    with store._connect() as conn:
        table_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        conversation_cols = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        run_cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        event_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        agent_cols = {row[1] for row in conn.execute("PRAGMA table_info(agents)")}

    assert "poller_heartbeats" not in table_names
    assert {"first_viewed_at", "presence_at", "interaction_mode", "polling_paused"}.isdisjoint(conversation_cols)
    assert {"hermes_conversation_id", "interaction_mode"}.isdisjoint(run_cols)
    assert "source_key" not in event_cols
    assert "hermes_agent_id" not in agent_cols


def test_existing_polling_pull_schema_is_hidden_from_public_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "relay.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                trigger_url TEXT NOT NULL,
                trigger_id TEXT NOT NULL,
                token_ref TEXT NOT NULL,
                hermes_agent_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                conversation_key TEXT NOT NULL UNIQUE,
                interaction_mode TEXT NOT NULL DEFAULT 'relay',
                first_viewed_at TEXT,
                presence_at TEXT,
                polling_paused INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                conversation_key TEXT NOT NULL,
                hermes_conversation_id TEXT,
                interaction_mode TEXT NOT NULL DEFAULT 'relay',
                idempotency_key TEXT NOT NULL,
                input_markdown TEXT NOT NULL,
                trigger_status TEXT NOT NULL DEFAULT 'draft',
                trigger_http_status INTEGER,
                trigger_x_request_id TEXT,
                conversation_url TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                request_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT,
                markdown TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                source_key TEXT
            );
            CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE plans (
                run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
                steps_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE poller_heartbeats (
                hermes_agent_id TEXT PRIMARY KEY,
                checked_at TEXT NOT NULL
            );
            INSERT INTO agents (id, name, trigger_url, trigger_id, token_ref, hermes_agent_id, created_at, updated_at)
            VALUES (1, 'default', 'https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger', 'agtch_test', 'env:TOKEN', 'agt_hermes', 'now', 'now');
            INSERT INTO conversations (id, agent_id, name, conversation_key, interaction_mode, first_viewed_at, presence_at, polling_paused, created_at, updated_at, archived_at)
            VALUES (1, 1, 'Old', 'old:key', 'pull', 'old', 'old', 1, 'now', 'now', NULL);
            INSERT INTO runs (id, request_id, agent_id, conversation_id, conversation_key, hermes_conversation_id, interaction_mode, idempotency_key, input_markdown, trigger_status, status, created_at, updated_at)
            VALUES (1, 'run_1', 1, 1, 'old:key', 'hconv', 'pull', 'idem_1', 'old task', 'accepted', 'accepted', 'now', 'now');
            INSERT INTO events (id, run_id, request_id, event_type, title, markdown, payload_json, created_at, source_key)
            VALUES (1, 1, 'run_1', 'progress', 'Polled', 'old polling event', '{}', 'now', 'node_1');
            """
        )

    store = RelayStore(db_path)

    retired_agent_fields = {"hermes_agent_id"}
    retired_conversation_fields = {"first_viewed_at", "presence_at", "interaction_mode", "polling_paused"}
    retired_run_fields = {"hermes_conversation_id", "interaction_mode"}
    agent_rows = [store.get_agent(1), store.get_agent_by_name("default"), store.list_agents()[0]]
    conversation_rows = [store.get_conversation(1), store.list_conversations()[0]]
    run_rows = [store.get_run(1), store.get_run_by_request_id("run_1"), store.list_runs_for_conversation(1)[0]]

    assert all(retired_agent_fields.isdisjoint(row) for row in agent_rows)
    assert all(retired_conversation_fields.isdisjoint(row) for row in conversation_rows)
    assert all(retired_run_fields.isdisjoint(row) for row in run_rows)
    assert "source_key" not in store.list_events(1)[0]


def test_update_conversation_rejects_retired_pull_fields(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    conv = store.create_conversation(agent_id=agent["id"], name="A", conversation_key="k:a")

    with pytest.raises(ValueError, match="unsupported field"):
        store.update_conversation(conv["id"], interaction_mode="pull")
    with pytest.raises(ValueError, match="unsupported field"):
        store.update_conversation(conv["id"], polling_paused=True)


def test_record_tool_trace_tags_active_turn_ord(tmp_path: Path) -> None:
    store = RelayStore(tmp_path / "relay.sqlite")
    agent = store.upsert_agent(
        name="default",
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        token_ref="env:TOKEN",
    )
    conv = store.create_conversation(agent_id=agent["id"], name="Trace", conversation_key="trace:key")
    run = store.create_run(
        agent_id=agent["id"],
        conversation_id=conv["id"],
        conversation_key=conv["conversation_key"],
        input_markdown="task",
        idempotency_key="run_1",
        request_id="run_1",
    )
    store.steer_run(run_id=run["id"], user_input="steer one")
    store.record_tool_trace(
        request_id="run_1",
        conversation_key="trace:key",
        tool="list_files",
        title="list_files",
    )

    events = store.list_events(run["id"])
    trace = next(e for e in events if json.loads(e["payload_json"]).get("trace"))
    assert json.loads(trace["payload_json"])["turn_ord"] == 1
