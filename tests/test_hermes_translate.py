from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hermes_translate as ht  # noqa: E402


HEADER_BLOCK = (
    "request_id: relay_20260627T145937Z_3c2b5f01864c\n"
    "conversation_key: workspace-agent-relay-mcp-mqwhk8vl\n"
    "relay_mcp: workspace-agent-relay-mcp\n"
)


def test_parse_relay_header_extracts_request_id_and_conversation_key():
    out = ht.parse_relay_header(HEADER_BLOCK)
    assert out["request_id"] == "relay_20260627T145937Z_3c2b5f01864c"
    assert out["conversation_key"] == "workspace-agent-relay-mcp-mqwhk8vl"
    # callback_token was removed from the protocol; the parser no longer looks for it.
    assert "callback_token" not in out


def test_parse_relay_header_missing_returns_empty():
    assert ht.parse_relay_header("just a user message, no relay header") == {}


def test_extract_user_task_initial_mode():
    text = HEADER_BLOCK + "\nCompletion contract:\nDo things...\n\nUser task:\nbuild a hello.txt"
    assert ht.extract_user_task(text) == "build a hello.txt"


def test_extract_user_task_continuation_mode():
    text = HEADER_BLOCK + "\nSame relay protocol as before: ...\n\nUser task:\n继续"
    assert ht.extract_user_task(text) == "继续"


def test_extract_user_task_steer_operator_added():
    text = HEADER_BLOCK + "\nThis is a follow-up ...\n\nOperator added:\n取消上面那个任务"
    assert ht.extract_user_task(text) == "取消上面那个任务"


def test_extract_user_task_answer_mode():
    text = HEADER_BLOCK + "\nThis is the operator's answer ...\n\nOperator answered:\n用方案 B"
    assert ht.extract_user_task(text) == "用方案 B"


def test_extract_user_task_fallback_strips_header_lines():
    # No delimiter: header lines are dropped, the rest is kept.
    text = HEADER_BLOCK + "a freeform user message\nwith two lines"
    task = ht.extract_user_task(text)
    assert "request_id" not in task
    assert "a freeform user message" in task


def test_is_agent_echo_detects_route_echo():
    echo = '{"agent_id":"agt_test","message":"hi"}'
    assert ht.is_agent_echo(echo) is True
    assert ht.is_agent_echo("正常的助手回复，不是 echo") is False


def test_infer_tool_name_image():
    parts = [{"content_type": "image_asset_pointer", "asset_pointer": "sediment://x"}]
    assert ht.infer_tool_name({"parts": parts}) == "image_generation"
    assert ht.infer_tool_name({"parts": ["plain text result"]}) == "tool"


def _user_node(body: str, ct: float = 1000.0, node_id: str = "u1") -> dict:
    return {"node_id": node_id, "role": "user", "content_type": "text", "parts": [body], "create_time": ct,
            "status": "finished_successfully", "is_current": False, "metadata": {}}


def _assistant_node(body: str, ct: float = 1001.0, current: bool = False, node_id: str = "a1") -> dict:
    return {"node_id": node_id, "role": "assistant", "content_type": "text", "parts": [body], "create_time": ct,
            "status": "finished_successfully", "is_current": current, "metadata": {}}


def _tool_node(ct: float = 1001.5, node_id: str = "t1", parts=None) -> dict:
    return {"node_id": node_id, "role": "tool", "content_type": "multimodal_text",
            "parts": parts or [{"content_type": "image_asset_pointer", "asset_pointer": "sediment://x"}],
            "create_time": ct, "status": "finished_successfully", "is_current": False, "metadata": {}}


def _make_db(path: Path, request_id: str, status: str = "done") -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY, request_id TEXT UNIQUE, status TEXT, "
        "agent_id INTEGER, conversation_key TEXT, created_at TEXT, completed_at TEXT);"
    )
    conn.execute(
        "INSERT INTO runs (id, request_id, status, agent_id, conversation_key, created_at, completed_at) "
        "VALUES (42, ?, ?, 1, 'ck', '2026-06-27T00:00:00+00:00', NULL)",
        (request_id, status),
    )
    conn.commit()
    conn.close()


def test_translate_record_binds_to_relay_run(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    rid = "relay_20260627T145937Z_3c2b5f01864c"
    _make_db(db, rid, status="done")
    record = {
        "conversation_id": "conv-1",
        "title": "Fu",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node(HEADER_BLOCK + "\nUser task:\ndo the thing", ct=1000.0),
            _assistant_node('{"agent_id":"agt_x","message":"do the thing"}', ct=1000.1),  # echo
            _assistant_node("all done, here is the result", ct=1002.0, current=True),
        ],
    }
    out = ht.translate_record(record, db)
    assert out["source"] == "polling"
    assert out["summary"]["turns"] == 1
    assert out["summary"]["bound_to_relay"] == 1
    turn = out["turns"][0]
    assert turn["request_id"] == rid
    assert turn["unbound"] is False
    assert turn["relay_run"] == {"id": 42, "status": "done", "agent_id": 1,
                                 "conversation_key": "ck",
                                 "created_at": "2026-06-27T00:00:00+00:00", "completed_at": None}
    assert turn["user_task"] == "do the thing"
    # Echo skipped; last assistant in a completed run -> result_candidate.
    assert [e["kind"] for e in turn["events"]] == ["result_candidate"]


def test_translate_record_unbound_when_request_id_absent_from_db(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    _make_db(db, "relay_other", status="done")
    record = {
        "conversation_id": "conv-2",
        "title": "Fu",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node(HEADER_BLOCK + "\nUser task:\ntask A"),
            _assistant_node("ok"),
        ],
    }
    out = ht.translate_record(record, db)
    turn = out["turns"][0]
    assert turn["unbound"] is True
    assert turn["relay_run"] is None
    assert out["summary"]["unbound"] == 1


def test_translate_record_no_relay_header_is_unbound(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    _make_db(db, "relay_other")
    record = {
        "conversation_id": "conv-3",
        "title": "scheduled",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node("[curl 直连探测] 连通性测试，请回复收到。"),  # no relay header
            _assistant_node("收到"),
        ],
    }
    out = ht.translate_record(record, db)
    turn = out["turns"][0]
    assert turn["request_id"] is None
    assert turn["unbound"] is True


def test_translate_record_multiple_turns_split_by_user_nodes(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    r1, r2 = "relay_t1", "relay_t2"
    _make_db(db, r1, status="done")
    # second run needs a separate row; rebuild db with both.
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO runs (id, request_id, status, agent_id, conversation_key, created_at, completed_at) "
        "VALUES (43, ?, 'waiting', 1, 'ck2', 't', NULL)",
        (r2,),
    )
    conn.commit()
    conn.close()
    record = {
        "conversation_id": "conv-4",
        "title": "Fu",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node(f"request_id: {r1}\nconversation_key: ck1\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\none", ct=1.0),
            _assistant_node('{"agent_id":"agt_x","message":"one"}', ct=1.1),
            _assistant_node("result one", ct=1.2),
            _user_node(f"request_id: {r2}\nconversation_key: ck2\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\ntwo", ct=2.0),
            _assistant_node('{"agent_id":"agt_x","message":"two"}', ct=2.1),
            _assistant_node("result two", ct=2.2, current=True),
        ],
    }
    out = ht.translate_record(record, db)
    assert out["summary"]["turns"] == 2
    assert out["summary"]["bound_to_relay"] == 2
    assert out["turns"][0]["request_id"] == r1
    assert out["turns"][0]["relay_run"]["id"] == 42
    assert out["turns"][1]["request_id"] == r2
    assert out["turns"][1]["relay_run"]["id"] == 43
    # Both completed -> last assistant in each turn is result_candidate.
    assert out["turns"][0]["events"][-1]["kind"] == "result_candidate"
    assert out["turns"][1]["events"][-1]["kind"] == "result_candidate"


def test_events_for_store_single_turn_completed_maps_last_to_result(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    rid = "relay_single"
    _make_db(db, rid, status="done")
    record = {
        "conversation_id": "c", "title": "t",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node(f"request_id: {rid}\nconversation_key: ck\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\ndo it", ct=1.0, node_id="u1"),
            _assistant_node('{"agent_id":"agt_x","message":"do it"}', ct=1.1, node_id="a0"),  # echo
            _assistant_node("intermediate reasoning", ct=1.2, node_id="a1"),
            _assistant_node("final answer", ct=1.3, node_id="a2", current=True),
        ],
    }
    evs = ht.events_for_store(record, db)
    # user + echo skipped; two assistant events remain.
    assert [e["event_type"] for e in evs] == ["progress", "result"]
    assert evs[0]["markdown"] == "intermediate reasoning"
    assert evs[0]["payload"] == {"polling": True, "turn_ord": 0, "mapping_ord": 2}
    assert evs[0]["create_time"] == 1.0
    assert evs[1]["markdown"] == "final answer"
    assert evs[1]["payload"] == {"status": "done", "polling": True, "turn_ord": 0, "mapping_ord": 3}
    assert evs[1]["create_time"] == 1.0
    # source_key = ChatGPT node id; run_id from lookup.
    assert evs[0]["source_key"] == "a1"
    assert evs[1]["source_key"] == "a2"
    assert all(e["run_id"] == 42 for e in evs)


def test_events_for_store_skips_unbound_turns(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    _make_db(db, "relay_other")
    record = {
        "conversation_id": "c", "title": "t",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node("no relay header here, just a task", ct=1.0),
            _assistant_node("a reply", ct=1.1),
        ],
    }
    assert ht.events_for_store(record, db) == []


def test_events_for_store_multi_turn_only_global_last_is_result(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    r1, r2 = "relay_t1", "relay_t2"
    _make_db(db, r1, status="done")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO runs (id, request_id, status, agent_id, conversation_key, created_at, completed_at) "
        "VALUES (43, ?, 'done', 1, 'ck2', 't', NULL)",
        (r2,),
    )
    conn.commit()
    conn.close()
    record = {
        "conversation_id": "c", "title": "t",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node(f"request_id: {r1}\nconversation_key: ck1\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\none", ct=1.0, node_id="u1"),
            _assistant_node('{"agent_id":"agt_x","message":"one"}', ct=1.1, node_id="a0"),
            _assistant_node("turn one final", ct=1.2, node_id="a1"),
            _user_node(f"request_id: {r2}\nconversation_key: ck2\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\ntwo", ct=2.0, node_id="u2"),
            _assistant_node('{"agent_id":"agt_x","message":"two"}', ct=2.1, node_id="a2"),
            _assistant_node("turn two final", ct=2.2, node_id="a3", current=True),
        ],
    }
    evs = ht.events_for_store(record, db)
    # Only the global last assistant ("turn two final") is a result; "turn one final" stays progress.
    results = [e for e in evs if e["event_type"] == "result"]
    progress = [e for e in evs if e["event_type"] == "progress"]
    assert len(results) == 1
    assert results[0]["markdown"] == "turn two final"
    assert results[0]["run_id"] == 43
    assert any(e["markdown"] == "turn one final" and e["run_id"] == 42 for e in progress)


def test_events_for_store_incomplete_turn_emits_no_result(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    rid = "relay_active"
    _make_db(db, rid, status="waiting")
    record = {
        "conversation_id": "c", "title": "t",
        "hermes_meta": {"fiber_status": "in_progress"},
        "messages": [
            _user_node(f"request_id: {rid}\nconversation_key: ck\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\ngoing", ct=1.0),
            _assistant_node('{"agent_id":"agt_x","message":"going"}', ct=1.1),
            _assistant_node("still working…", ct=1.2, current=True),
        ],
    }
    evs = ht.events_for_store(record, db)
    assert [e["event_type"] for e in evs] == ["progress"]
    assert evs[0]["markdown"] == "still working…"


def test_events_for_store_tool_node_becomes_trace_progress(tmp_path: Path):
    db = tmp_path / "relay.sqlite"
    rid = "relay_tool"
    _make_db(db, rid, status="done")
    record = {
        "conversation_id": "c", "title": "t",
        "hermes_meta": {"fiber_status": "completed"},
        "messages": [
            _user_node(f"request_id: {rid}\nconversation_key: ck\nrelay_mcp: workspace-agent-relay-mcp\n\nUser task:\ndraw", ct=1.0),
            _assistant_node('{"agent_id":"agt_x","message":"draw"}', ct=1.1),
            _tool_node(ct=1.2, node_id="t1"),
            _assistant_node("done drawing", ct=1.3, current=True, node_id="a1"),
        ],
    }
    evs = ht.events_for_store(record, db)
    tool_ev = next(e for e in evs if e["source_key"] == "t1")
    assert tool_ev["event_type"] == "progress"
    assert tool_ev["payload"]["trace"] is True
    assert tool_ev["payload"]["tool"] == "image_generation"
    # The final assistant message is still the synthesized result.
    assert any(e["event_type"] == "result" and e["markdown"] == "done drawing" for e in evs)
