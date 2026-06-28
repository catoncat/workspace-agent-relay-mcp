#!/usr/bin/env python3
"""Live demo: trigger a relay run (original protocol), poll the real ChatGPT
conversation via CDP, and print the merged (callback + polling) timeline for
that one run — no source labels, exactly as the UI would render it.

Run from repo root:
  .venv/bin/python scripts/hermes_live_demo.py
  .venv/bin/python scripts/hermes_live_demo.py --task "你的任务"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from hermes_fetch import PWHermes  # noqa: E402
from hermes_poller import flatten_mapping, render_parts  # noqa: E402
from hermes_translate import translate_record, is_agent_echo  # noqa: E402

RELAY = os.environ.get("RELAY_URL", "http://127.0.0.1:8799")
CDP = os.environ.get("HERMES_CDP", "http://127.0.0.1:9223")
HERMES_AGT = os.environ.get("HERMES_AGENT_ID", "")  # set in .env or pass --agent
DB = os.path.expanduser(os.environ.get("HERMES_DB", "~/.workspace-agent-relay-mcp/relay.sqlite"))
RELAY_AGENT_ID = int(os.environ.get("RELAY_AGENT_ID", "2"))
DEFAULT_TASK = "帮我数一下 ~/.workspace-agent-relay-mcp/hermes-poller 目录下有多少个 .json 文件，把数字告诉我。"


def load_auth_token() -> str:
    env = os.environ.get("WORKSPACE_AGENT_RELAY_AUTH_TOKEN", "").strip()
    if env:
        return env
    for cand in (Path.cwd() / ".env",):
        if cand.is_file():
            for ln in cand.read_text().splitlines():
                if ln.startswith("WORKSPACE_AGENT_RELAY_AUTH_TOKEN="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no WORKSPACE_AGENT_RELAY_AUTH_TOKEN found")


def relay_post(path: str, body: dict, token: str) -> dict:
    req = urllib.request.Request(
        RELAY + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"relay {path} failed: HTTP {e.code} {e.read().decode('utf-8','replace')[:300]}")


def relay_events(run_id: int) -> list[dict]:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT event_type, title, markdown, created_at FROM events WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def merged_timeline(run_id: int, turn: dict) -> None:
    rows: list[tuple] = []
    for e in relay_events(run_id):
        rows.append((e["created_at"], e["event_type"], e["title"] or "", (e["markdown"] or "")[:160].replace("\n", " ")))
    for ev in turn.get("events", []):
        ct = ev.get("create_time")
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ct)) if isinstance(ct, (int, float)) else "9"
        kind = ev["kind"]
        label = {"progress": "progress", "result_candidate": "result", "trace": "trace"}.get(kind, kind)
        txt = (ev.get("text") or ev.get("summary") or "")[:160].replace("\n", " ")
        rows.append((ts, label, "", txt))
    rows.sort(key=lambda r: r[0])
    print(f"\n===== merged timeline (run {run_id}, no source labels) =====")
    for ts, typ, title, txt in rows:
        print(f"  {ts}  [{typ:7}] {title}{' | ' if title else ''}{txt}")


def find_our_conv(h: PWHermes, request_id: str, depth: int = 6) -> tuple[str, dict] | None:
    items, _ = h.list_conversations(HERMES_AGT, depth)
    for it in items:
        cid = it.get("id")
        conv = h.fetch_conversation(cid)
        if not conv:
            continue
        for nid, node in (conv.get("mapping") or {}).items():
            msg = (node or {}).get("message") or {}
            text = render_parts(((msg.get("content") or {}).get("parts")))
            if request_id in text:
                return cid, conv
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Live demo: trigger + poll + merged timeline.")
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--interval", type=float, default=8.0)
    args = ap.parse_args()

    token = load_auth_token()
    ck = f"demo:{secrets.token_hex(4)}"
    print(f"== creating conversation (agent {RELAY_AGENT_ID}, key {ck}) ==")
    conv = relay_post("/api/conversations", {"agent_id": RELAY_AGENT_ID, "name": "polling live demo", "conversation_key": ck}, token)
    conv_id = int(conv["id"])
    print(f"== triggering run: {args.task!r} ==")
    run = relay_post(f"/api/conversations/{conv_id}/runs", {"input_markdown": args.task}, token)
    request_id = run["request_id"]
    run_id = int(run["id"])
    print(f"   run_id={run_id} request_id={request_id} status={run['status']} trigger={run.get('trigger_status')}")
    print(f"   conversation_url={run.get('conversation_url')}")

    # Extract ChatGPT conversation id from the trigger response when available.
    cid = None
    if run.get("conversation_url"):
        m = re.search(r"/c/([0-9a-f-]{36})", run["conversation_url"])
        if m:
            cid = m.group(1)

    print(f"\n== CDP polling (interval={args.interval}s timeout={args.timeout}s) ==")
    if cid:
        print(f"   target conv from conversation_url: {cid}")
    deadline = time.time() + args.timeout
    conv = None
    prev_nodes = -1
    stable = 0
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        page = next((c for c in ctx.pages if "chatgpt.com" in c.url), None) or ctx.new_page()
        h = PWHermes(page)
        if not h.wait_for_session(timeout=30):
            print("! no session")
            return 2
        while time.time() < deadline:
            try:
                if cid is None:
                    found = find_our_conv(h, request_id)
                    if found:
                        cid, conv = found
                        print(f"   found our conversation by request_id: {cid}")
                if cid:
                    conv = h.fetch_conversation(cid)
                    msgs = flatten_mapping((conv or {}).get("mapping"), (conv or {}).get("current_node"))
                    asyn = (conv or {}).get("async_status")
                    real = [m for m in msgs if m["role"] == "assistant"
                            and (render_parts(m["parts"]) or "").strip()
                            and not is_agent_echo(render_parts(m["parts"]))]
                    print(f"   [{time.strftime('%H:%M:%S')}] nodes={len(msgs)} async={asyn} real_assistant={len(real)}")
                    if len(msgs) == prev_nodes:
                        stable += 1
                    else:
                        stable = 0
                        prev_nodes = len(msgs)
                    # done when node count is stable for 2 polls AND a real reply landed
                    if stable >= 2 and real:
                        break
            except Exception as e:
                print(f"   poll warn: {e}")
            time.sleep(args.interval)
        if conv is None:
            print("! conversation not found before timeout — try longer --timeout")
            return 3

    # Translate + merge.
    record = {
        "conversation_id": cid, "title": conv.get("title"),
        "create_time": conv.get("create_time"), "current_node": conv.get("current_node"),
        "hermes_meta": {"fiber_status": "completed"},
        "messages": flatten_mapping(conv.get("mapping"), conv.get("current_node")),
    }
    translated = translate_record(record, Path(DB))
    turn = next((t for t in translated["turns"] if t.get("request_id") == request_id), None)
    print(f"\n== relay callback events for run {run_id} ==")
    evs = relay_events(run_id)
    for e in evs:
        print(f"   [{e['event_type']}] {e['title'] or ''}  | {(e['markdown'] or '')[:120].replace(chr(10),' ')}")
    print(f"   ({len(evs)} callback events)")
    if turn:
        print(f"\n== polling-derived turn (events={len(turn['events'])}) ==")
        for ev in turn["events"]:
            txt = (ev.get("text") or ev.get("summary") or "")[:120].replace("\n", " ")
            print(f"   <{ev['kind']}> {txt}")
        merged_timeline(run_id, turn)
    else:
        print("! polling turn for our request_id not found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
