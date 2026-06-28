#!/usr/bin/env python3
"""EXPERIMENTAL — Translate fetched Hermes conversations into relay-style events.

Reads the records produced by hermes_poller.py / hermes_poller_cdp.py
(<out_dir>/<conv_id>.json, each with a flattened `messages` list) and produces a
relay-event-like stream per conversation, written to <out_dir>/<conv_id>.events.json.

Non-invasive by design: this does NOT write into the relay store. It only reads
the relay SQLite (read-only) to correlate each turn's `request_id` to a relay run,
so polling-derived visibility can be lined up with the callback-driven dashboard.

Per-turn translation (see docs/research §4.4):
  - user node  -> parse `request_id` / `conversation_key` from the relay header
    (build_trigger_input format); extract the user task body; correlate to a
    relay run by request_id (run_id + status) or mark `unbound`.
  - assistant first-after-user  -> `{"agent_id":...,"message":...}` route echo: skip.
  - assistant subsequent        -> `progress` narration; the last one in a completed
    turn is flagged `result_candidate`.
  - tool nodes                 -> `trace` (tool name inferred from content; e.g.
    image_asset_pointer -> image_generation).

`events_for_store` produces the store-ready event list (mapped onto existing
relay event_types) that the poller POSTs to /internal/runs/{id}/polling-events.
See docs/superpowers/specs/2026-06-28-polling-merge.md.

Run:
  .venv/bin/python scripts/hermes_translate.py
  .venv/bin/python scripts/hermes_translate.py --cid 6a3fe55e-bd64-8320-ba7d-47a0e34dfd89
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hermes_poller import render_parts  # noqa: E402

DEFAULT_RECORDS_DIR = "~/.workspace-agent-relay-mcp/hermes-poller"
DEFAULT_DB = "~/.workspace-agent-relay-mcp/relay.sqlite"

_HEADER_RE = {
    "request_id": re.compile(r"^request_id:\s*(\S+)\s*$", re.MULTILINE),
    "conversation_key": re.compile(r"^conversation_key:\s*(\S+)\s*$", re.MULTILINE),
}
# Delimiters that precede the actual user task body in build_trigger_input output,
# ordered by how they appear. We take the LAST match's trailing text.
_TASK_DELIMITERS = ["User task:", "Operator added:", "Operator answered:"]
_ECHO_RE = re.compile(r'^\s*\{\s*"agent_id"\s*:\s*"agt_', re.DOTALL)


def parse_relay_header(text: str) -> dict[str, str]:
    """Extract request_id / conversation_key from a user node body."""
    out = {}
    for key, rx in _HEADER_RE.items():
        m = rx.search(text)
        if m:
            out[key] = m.group(1).strip()
    return out


def extract_user_task(text: str) -> str:
    """Strip the relay header + contract boilerplate; return the user's actual task."""
    best = -1
    for delim in _TASK_DELIMITERS:
        idx = text.rfind(delim)
        if idx != -1:
            body_start = idx + len(delim)
            if body_start > best:
                best = body_start
    if best >= 0:
        return text[best:].strip()
    # Fallback: drop the four header lines, keep the rest.
    lines = []
    for ln in text.splitlines():
        if any(rx.match(ln) for rx in _HEADER_RE.values()):
            continue
        if ln.strip() == "relay_mcp: workspace-agent-relay-mcp":
            continue
        lines.append(ln)
    return "\n".join(lines).strip()


def is_agent_echo(text: str) -> bool:
    return bool(_ECHO_RE.match(text))


def infer_tool_name(node: dict) -> str:
    parts = node.get("parts") or []
    blob = json.dumps(parts, ensure_ascii=False)
    if "image_asset_pointer" in blob:
        return "image_generation"
    if "dalle" in blob:
        return "image_generation"
    return "tool"


def _short(s: str, n: int = 200) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def lookup_run(db_path: Path, request_id: str) -> dict | None:
    """Read-only correlation to the relay store. Returns {id, status, agent_id, conversation_key} or None."""
    if not request_id or not db_path.is_file():
        return None
    try:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute(
                "SELECT id, status, agent_id, conversation_key, created_at, completed_at "
                "FROM runs WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"  ! relay db lookup failed: {exc}", file=sys.stderr)
        return None
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "status": row[1],
        "agent_id": int(row[2]),
        "conversation_key": row[3],
        "created_at": row[4],
        "completed_at": row[5],
    }


def translate_record(record: dict, db_path: Path) -> dict:
    msgs = record.get("messages") or []
    fiber_status = (record.get("hermes_meta") or {}).get("fiber_status")
    turns: list[dict] = []
    current: dict | None = None
    seen_echo = False

    def finish_turn() -> None:
        nonlocal current
        if current is None:
            return
        evs = current["events"]
        # Flag the last progress as result_candidate when the run completed.
        if fiber_status == "completed" and evs:
            last = evs[-1]
            if last["kind"] == "progress":
                last["kind"] = "result_candidate"
        turns.append(current)
        current = None

    for m in msgs:
        role = m.get("role")
        text = render_parts(m.get("parts"))
        ct = m.get("create_time")
        if role == "user":
            finish_turn()
            header = parse_relay_header(text)
            rid = header.get("request_id", "")
            ck = header.get("conversation_key", "")
            relay_run = lookup_run(db_path, rid) if rid else None
            current = {
                "request_id": rid or None,
                "conversation_key": ck or None,
                "relay_run": relay_run,
                "unbound": relay_run is None,
                "user_task": extract_user_task(text) if (rid or text) else "",
                "create_time": ct,
                "events": [],
            }
            seen_echo = False
            continue
        if current is None:
            # Messages before any user node (rare): ignore.
            continue
        if role == "assistant":
            if not seen_echo and is_agent_echo(text):
                seen_echo = True
                continue
            seen_echo = True  # subsequent assistants are real
            current["events"].append({
                "kind": "progress",
                "create_time": ct,
                "text": _short(text, 1000),
                "is_current": bool(m.get("is_current")),
            })
        elif role == "tool":
            current["events"].append({
                "kind": "trace",
                "create_time": ct,
                "tool": infer_tool_name(m),
                "summary": _short(json.dumps(m.get("parts"), ensure_ascii=False), 200),
                "is_current": bool(m.get("is_current")),
            })
        else:
            current["events"].append({
                "kind": "other",
                "role": role,
                "create_time": ct,
                "text": _short(text, 1000),
            })
    finish_turn()

    bound = [t for t in turns if not t["unbound"]]
    return {
        "conversation_id": record.get("conversation_id"),
        "title": record.get("title"),
        "hermes_meta": record.get("hermes_meta"),
        "source": "polling",
        "turns": turns,
        "summary": {
            "turns": len(turns),
            "bound_to_relay": len(bound),
            "unbound": len(turns) - len(bound),
        },
    }


def events_for_store(record: dict, db_path: Path) -> list[dict]:
    """Produce store-ready events (mapped onto existing relay event_types) for
    the poller to POST to /internal/runs/{id}/polling-events.

    Only turns bound to a relay run produce events. Mapping (see spec §5):
      - agent visible message (non-echo) -> progress (markdown = text)
      - cloud tool node (image/code)     -> progress (trace payload)
      - global last agent message when fiber completed -> result (synthesized)
      - user nodes / agent echo          -> skipped
    """
    msgs = record.get("messages") or []
    hermes_meta = record.get("hermes_meta") or {}
    fiber_completed = hermes_meta.get("fiber_status") == "completed"

    # Global last non-echo assistant message node id (the conversation's final
    # reply). Only this one becomes a synthesized result; every other assistant
    # message is progress. Earlier turns' final messages stay progress — their
    # callback result (if any) already renders the terminal, and the read-side
    # merge drops this synthesized result when a callback result exists.
    last_assistant_node_id = None
    for m in reversed(msgs):
        if m.get("role") == "assistant" and not is_agent_echo(render_parts(m.get("parts"))):
            last_assistant_node_id = m.get("node_id")
            break

    events: list[dict] = []
    current_run_id: int | None = None
    turn_ord = -1
    turn_anchor_ct: float | None = None
    seen_echo = False
    mapping_ord = -1
    for m in msgs:
        mapping_ord += 1
        role = m.get("role")
        node_id = m.get("node_id")
        ct = m.get("create_time")
        if role == "user":
            header = parse_relay_header(render_parts(m.get("parts")))
            rid = header.get("request_id", "")
            run = lookup_run(db_path, rid) if rid else None
            if run:
                current_run_id = int(run["id"])
                turn_ord += 1
                turn_anchor_ct = float(ct) if isinstance(ct, (int, float)) else None
            else:
                current_run_id = None
                turn_ord = -1
                turn_anchor_ct = None
            seen_echo = False
            continue
        if current_run_id is None:
            continue
        sort_ct = turn_anchor_ct if turn_anchor_ct is not None else ct
        poll_meta = {"polling": True, "turn_ord": turn_ord, "mapping_ord": mapping_ord}
        if role == "assistant":
            text = render_parts(m.get("parts"))
            if not seen_echo and is_agent_echo(text):
                seen_echo = True
                continue
            seen_echo = True
            if not text.strip():
                continue
            if fiber_completed and node_id == last_assistant_node_id:
                events.append({
                    "run_id": current_run_id,
                    "source_key": str(node_id),
                    "event_type": "result",
                    "title": None,
                    "markdown": _short(text, 4000),
                    "payload": {"status": "done", **poll_meta},
                    "create_time": sort_ct,
                })
            else:
                events.append({
                    "run_id": current_run_id,
                    "source_key": str(node_id),
                    "event_type": "progress",
                    "title": None,
                    "markdown": _short(text, 4000),
                    "payload": poll_meta,
                    "create_time": sort_ct,
                })
        elif role == "tool":
            tool = infer_tool_name(m)
            events.append({
                "run_id": current_run_id,
                "source_key": str(node_id),
                "event_type": "progress",
                "title": tool,
                "markdown": f"✓ {tool}",
                "payload": {
                    "trace": True,
                    "tool": tool,
                    "title": tool,
                    "ok": True,
                    **poll_meta,
                },
                "create_time": sort_ct,
            })
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description="Translate fetched Hermes records into relay-style events.")
    ap.add_argument("--records-dir", default=os.environ.get("HERMES_OUT_DIR", DEFAULT_RECORDS_DIR))
    ap.add_argument("--db", default=os.environ.get("HERMES_DB", DEFAULT_DB))
    ap.add_argument("--cid", default="", help="translate only this conversation id (else all *.json except seen)")
    ap.add_argument("--out-dir", default="", help="events output dir (default: records-dir)")
    args = ap.parse_args()

    records_dir = Path(os.path.expanduser(args.records_dir))
    db_path = Path(os.path.expanduser(args.db))
    out_dir = Path(os.path.expanduser(args.out_dir)) if args.out_dir else records_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.cid:
        targets = [records_dir / f"{args.cid}.json"]
    else:
        targets = sorted(p for p in records_dir.glob("*.json") if p.stem != "seen")
    targets = [p for p in targets if p.is_file()]
    if not targets:
        print(f"no records found in {records_dir}", file=sys.stderr)
        return 1

    print(f"== hermes_translate: {len(targets)} record(s); db={db_path} ==")
    n_turns = n_bound = 0
    for path in targets:
        record = json.loads(path.read_text())
        translated = translate_record(record, db_path)
        (out_dir / f"{path.stem}.events.json").write_text(
            json.dumps(translated, ensure_ascii=False, indent=2)
        )
        s = translated["summary"]
        n_turns += s["turns"]
        n_bound += s["bound_to_relay"]
        cid = translated["conversation_id"]
        print(
            f"  - {cid} turns={s['turns']} bound={s['bound_to_relay']} unbound={s['unbound']} -> {path.stem}.events.json"
        )
        for t in translated["turns"]:
            tag = f"      turn req={t['request_id'] or '(none)'}"
            tag += f" run={t['relay_run']['id']}/{t['relay_run']['status']}" if t["relay_run"] else " run=UNBOUND"
            tag += f" events={len(t['events'])} task={_short(t['user_task'], 60)!r}"
            print(tag)
    print(f"== done: {n_turns} turns, {n_bound} bound to relay runs ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
