#!/usr/bin/env python3
"""Experimental: poll a ChatGPT Workspace Agent's runs via the internal hermes
backend-api and read back full conversation content (the `mapping` message tree).

Why this exists
---------------
The public Workspace Agents API (api.chatgpt.com/v1/workspace_agents/{agtch}/trigger)
is fire-and-forget: 202, no run id, no result. The relay currently fills that gap
by having the agent call back via MCP. This script explores a *second*, callback-free
path: use the browser session to (a) list the agent's runs + status from hermes, and
(b) fetch each run's full message tree from /backend-api/conversation/{id}, then
linearize it into the relay's plan/progress/result-shaped records.

Auth
----
Browser session cookies (export chatgpt.com cookies to JSON). Refreshes the session
JWT via /api/auth/session. No agent access token, no agent cooperation needed.

Scope
-----
Read-only GETs only. Experimental; depends on undocumented internal endpoints that
can change without notice. Confirmed working as of 2026-06-28 on a Business account
from the same machine that exported the cookies (no cf_clearance required that day).

Usage
-----
    python3 scripts/hermes_readback.py --agent-id agt_xxx
        [--limit 10]
        [--cookie-file ~/Downloads/chatgpt.com.cookies.json]
        [--dump-dir /tmp/hermes-dump]
        [--state ~/.workspace-agent-relay-mcp/hermes_readback.state.json]
        [--full]   # do not truncate message parts in output

Exit codes: 0 ok; 2 auth/cookie problem; 3 upstream error.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
SESSION_URL = "https://chatgpt.com/api/auth/session"
HERMES_CONV_LIST = "https://chatgpt.com/backend-api/hermes/agent/{agent_id}/conversations?limit={limit}"
CONV_DETAIL = "https://chatgpt.com/backend-api/conversation/{conv_id}"
DEFAULT_COOKIE_FILE = str(Path.home() / "Downloads/chatgpt.com.cookies.json")
DEFAULT_STATE = str(Path.home() / ".workspace-agent-relay-mcp/hermes_readback.state.json")


# ---------- transport ----------

def load_cookie_header(path: str) -> str:
    data = json.load(open(path))
    return "; ".join(f"{c['name']}={c['value']}" for c in data if "chatgpt.com" in c.get("domain", ""))


def http(method: str, url: str, headers: dict, body: bytes | None = None, timeout: float = 30.0):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {}, f"{type(e).__name__}: {e}"


def jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        pad = "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return {}


def get_session(cookie: str) -> tuple[str, str]:
    """Return (access_token_jwt, chatgpt_account_id) from /api/auth/session."""
    s, _, b = http("GET", SESSION_URL, {"User-Agent": UA, "Cookie": cookie, "Accept": "application/json"})
    if s != 200:
        return "", ""
    try:
        jwt = json.loads(b).get("accessToken") or json.loads(b).get("access_token") or ""
    except Exception:
        jwt = ""
    if not jwt:
        return "", ""
    payload = jwt_payload(jwt)
    auth_ns = payload.get("https://api.openai.com/auth", {}) or {}
    account_id = auth_ns.get("chatgpt_account_id") or payload.get("chatgpt_account_id") or ""
    return jwt, account_id


# ---------- hermes / conversation ----------

def list_conversations(jwt: str, account_id: str, cookie: str, agent_id: str, limit: int) -> list[dict]:
    url = HERMES_CONV_LIST.format(agent_id=agent_id, limit=limit)
    s, _, b = http("GET", url, {
        "User-Agent": UA, "Authorization": f"Bearer {jwt}",
        "chatgpt-account-id": account_id, "Cookie": cookie,
        "Accept": "application/json",
        "Referer": f"https://chatgpt.com/agents/a/{agent_id}",
    })
    if s != 200:
        raise RuntimeError(f"list conversations HTTP {s}: {b[:300]}")
    j = json.loads(b)
    return j.get("items", []) or []


def get_conversation(jwt: str, account_id: str, cookie: str, agent_id: str, conv_id: str) -> dict:
    url = CONV_DETAIL.format(conv_id=conv_id)
    s, _, b = http("GET", url, {
        "User-Agent": UA, "Authorization": f"Bearer {jwt}",
        "chatgpt-account-id": account_id, "Cookie": cookie,
        "Accept": "application/json",
        "Referer": f"https://chatgpt.com/agents/a/{agent_id}",
    })
    if s != 200:
        raise RuntimeError(f"get conversation {conv_id} HTTP {s}: {b[:300]}")
    return json.loads(b)


# ---------- mapping -> linear records ----------

def linearize(mapping: dict, current_node: str | None) -> list[dict]:
    """Walk parent pointers from current_node up to root; return root..current list."""
    if not mapping:
        return []
    # find current_node if not given: pick a node that is nobody's parent (leaf-ish)
    if not current_node or current_node not in mapping:
        children_ids = {c for n in mapping.values() for c in (n.get("children") or [])}
        leaves = [mid for mid in mapping if mid not in children_ids]
        current_node = leaves[-1] if leaves else next(iter(mapping))
    chain = []
    cur = current_node
    seen = set()
    while cur and cur in mapping and cur not in seen:
        seen.add(cur)
        chain.append(mapping[cur])
        cur = mapping[cur].get("parent")
    chain.reverse()
    return chain


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f" …(+{len(s) - n} chars)"


def node_record(node: dict, full: bool) -> dict | None:
    """Compact a mapping node into a relay-event-shaped record."""
    msg = (node or {}).get("message") or {}
    if not msg:
        return {"kind": "structural", "id": node.get("id")}
    role = (msg.get("author") or {}).get("role", "?")
    content = msg.get("content") or {}
    content_type = content.get("content_type")
    parts = content.get("parts") or []
    limit = 10**9 if full else 600
    compact_parts = []
    for p in parts:
        if isinstance(p, str):
            compact_parts.append(_truncate(p, limit))
        elif isinstance(p, dict):
            compact_parts.append({k: (_truncate(str(v), limit) if isinstance(v, str) else v) for k, v in list(p.items())[:8]})
        else:
            compact_parts.append(_truncate(str(p), limit))
    md = msg.get("metadata") or {}
    rec = {
        "id": msg.get("id") or node.get("id"),
        "role": role,
        "create_time": msg.get("create_time"),
        "status": msg.get("status"),
        "content_type": content_type,
        "parts": compact_parts,
        "metadata_keys": list(md.keys())[:12] if md else [],
    }
    # surface tool-call-ish signals so we can later map to relay plan/progress
    for k in ("message_type", "aggregate_result", "finish_details", "tool_calls", "is_complete", "request_id", "parent_id"):
        if k in md:
            rec[k] = md[k]
    if role == "tool":
        rec["kind"] = "tool_result"
    elif content_type == "code":
        rec["kind"] = "code/tool_use"
    elif role == "assistant":
        rec["kind"] = "assistant"
    elif role == "user":
        rec["kind"] = "user"
    else:
        rec["kind"] = role
    return rec


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="Poll a Workspace Agent's runs and read back conversation content.")
    ap.add_argument("--agent-id", required=True, help="hermes agent id, agt_...")
    ap.add_argument("--limit", type=int, default=10, help="how many recent conversations to list (default 10)")
    ap.add_argument("--cookie-file", default=DEFAULT_COOKIE_FILE, help="chatgpt.com cookies JSON export")
    ap.add_argument("--dump-dir", default="", help="if set, dump each conversation's raw JSON here")
    ap.add_argument("--state", default="", help="if set, only print conversations not seen in this state file")
    ap.add_argument("--full", action="store_true", help="do not truncate message parts")
    args = ap.parse_args()

    if not Path(args.cookie_file).is_file():
        print(f"cookie file not found: {args.cookie_file}", file=sys.stderr)
        return 2
    cookie = load_cookie_header(args.cookie_file)
    jwt, account_id = get_session(cookie)
    if not jwt:
        print("could not obtain session JWT from /api/auth/session (cookies expired?)", file=sys.stderr)
        return 2
    if not account_id:
        print("warning: could not extract chatgpt_account_id from JWT; hermes calls will likely 401", file=sys.stderr)
    print(f"# session ok: jwt len={len(jwt)} account_id={account_id}\n", file=sys.stderr)

    seen: set[str] = set()
    if args.state:
        sp = Path(args.state)
        if sp.is_file():
            try:
                seen = set(json.loads(sp.read_text()).get("seen_ids", []))
            except Exception:
                seen = set()

    try:
        items = list_conversations(jwt, account_id, cookie, args.agent_id, args.limit)
    except RuntimeError as e:
        print(f"list_conversations failed: {e}", file=sys.stderr)
        return 3
    print(f"# {len(items)} conversation(s) listed for {args.agent_id}\n", file=sys.stderr)

    dump_dir = Path(args.dump_dir) if args.dump_dir else None
    if dump_dir:
        dump_dir.mkdir(parents=True, exist_ok=True)

    printed = 0
    for item in items:
        cid = item.get("id")
        if not cid:
            continue
        if args.state and cid in seen:
            continue
        inv = item.get("invocation") or {}
        header = {
            "conversation_id": cid,
            "title": item.get("title"),
            "fiber_id": item.get("fiber_id"),
            "fiber_status": item.get("fiber_status"),
            "fiber_is_responding": item.get("fiber_is_responding"),
            "invocation_type": inv.get("type"),
            "is_scheduled": inv.get("is_scheduled"),
            "last_used_at": item.get("last_used_at"),
        }
        try:
            conv = get_conversation(jwt, account_id, cookie, args.agent_id, cid)
        except RuntimeError as e:
            print(f"# get_conversation {cid} failed: {e}", file=sys.stderr)
            continue
        mapping = conv.get("mapping") or {}
        current_node = conv.get("current_node")
        records = [r for r in (node_record(n, args.full) for n in linearize(mapping, current_node)) if r]

        if dump_dir:
            (dump_dir / f"{cid}.json").write_text(json.dumps(conv, ensure_ascii=False, indent=2))
        print(json.dumps({"header": header, "messages": records}, ensure_ascii=False, indent=2))
        print()
        printed += 1
        if args.state:
            seen.add(cid)

    if args.state:
        Path(args.state).parent.mkdir(parents=True, exist_ok=True)
        Path(args.state).write_text(json.dumps({"seen_ids": sorted(seen)}, ensure_ascii=False, indent=2))
        print(f"# state updated: {args.state} ({len(seen)} seen)", file=sys.stderr)
    print(f"# printed {printed} conversation(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
