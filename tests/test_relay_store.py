from pathlib import Path
import hashlib
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
