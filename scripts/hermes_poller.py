#!/usr/bin/env python3
"""EXPERIMENTAL — Hermes conversation poller + readback (not wired into the relay yet).

What it does:
  1. Loads browser cookies (chatgpt.com export JSON) + refreshes the session JWT
     via /api/auth/session.
  2. Lists an agent's runs via /backend-api/hermes/agent/{agt_id}/conversations.
  3. For each run not yet seen, fetches /backend-api/conversation/{id} and flattens
     the `mapping` message tree into an ordered, structured form.
  4. Saves each run to <out_dir>/<conv_id>.json and prints a summary.

Purpose: probe the "mapping -> relay event" translation — the main unknown for a
polling-based result retriever that would complement the relay's MCP-callback path
and cover scheduled runs (which bypass build_trigger_input / callback_token).

Auth: browser session only (cookies + session JWT + chatgpt-account-id). The agent
access token CANNOT read conversations (verified: 401 no_matching_rule on hermes).

Run:
  cp ~/Downloads/chatgpt.com.cookies.json ~/.workspace-agent-relay-mcp/hermes-cookies.json
  .venv/bin/python scripts/hermes_poller.py --limit 20
  # loop mode:
  .venv/bin/python scripts/hermes_poller.py --interval 60 --limit 20

Env overrides:
  HERMES_COOKIE_FILE   (default ~/.workspace-agent-relay-mcp/hermes-cookies.json)
  HERMES_AGENT_ID      (required if --agent not passed; e.g. agt_xxx)
  HERMES_ACCOUNT_ID    (required if --account not passed; your chatgpt account uuid)
  HERMES_OUT_DIR       (default ~/.workspace-agent-relay-mcp/hermes-poller)

Standalone by design — no imports from the relay package — so it can be validated
in isolation before being wired into the relay event model.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
DEFAULTS = {
    "cookie_file": "~/.workspace-agent-relay-mcp/hermes-cookies.json",
    "agent_id": "",
    "account_id": "",
    "out_dir": "~/.workspace-agent-relay-mcp/hermes-poller",
}
SESSION_URL = "https://chatgpt.com/api/auth/session"


def env(key: str, default: str) -> str:
    return os.environ.get(key, os.path.expanduser(default))


def redact(s: str) -> str:
    s = re.sub(r"eyJ[A-Za-z0-9_-]{20,}[A-Za-z0-9_-]*", "[JWT]", s)
    s = re.sub(r"\b[A-Za-z0-9_-]{48,}\b", "[TOKEN]", s)
    return s


def load_cookie_header(path: str) -> str:
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get("cookies") or data.get("data") or []
    pairs = [f"{c['name']}={c['value']}" for c in data if "chatgpt.com" in c.get("domain", "")]
    return "; ".join(pairs)


def http_get(url: str, headers: dict, timeout: float = 30.0) -> tuple[int, dict, str]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {}, f"{type(e).__name__}: {e}"


class Hermes:
    def __init__(self, cookie_file: str, agent_id: str, account_id: str, cf_clearance: str = ""):
        self.cookie = load_cookie_header(cookie_file)
        # cf_clearance is long-lived (observed ~1yr expiry) but the browser export
        # often omits it (HttpOnly+Secure). Let it be supplied via env/arg so it
        # survives cookie-jar re-exports; append only if the jar didn't include it.
        if cf_clearance and "cf_clearance=" not in self.cookie:
            self.cookie = f"{self.cookie}; cf_clearance={cf_clearance}"
        self.agent_id = agent_id
        self.account_id = account_id
        self.jwt = ""
        self._refresh_jwt()

    def _refresh_jwt(self) -> None:
        s, _, b = http_get(SESSION_URL, {"User-Agent": UA, "Cookie": self.cookie, "Accept": "application/json"})
        if s != 200:
            raise SystemExit(f"session refresh failed: HTTP {s}; re-export chatgpt.com cookies.\n  {redact(b[:200])}")
        self.jwt = json.loads(b).get("accessToken", "")
        if not self.jwt:
            raise SystemExit(f"no accessToken in /api/auth/session response; cookies may be stale.\n  keys: {list(json.loads(b).keys())}")

    def _headers(self) -> dict:
        return {
            "User-Agent": UA,
            "Authorization": f"Bearer {self.jwt}",
            "chatgpt-account-id": self.account_id,
            "Cookie": self.cookie,
            "Accept": "application/json",
            "Referer": f"https://chatgpt.com/agents/a/{self.agent_id}",
        }

    def _get(self, url: str, retry_on_401: bool = True) -> tuple[int, str]:
        s, _, b = http_get(url, self._headers())
        if s == 401 and retry_on_401:
            self._refresh_jwt()
            s, _, b = http_get(url, self._headers())
        return s, b

    def list_conversations(self, limit: int, cursor: str | None = None) -> tuple[list[dict], str | None]:
        params = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        url = f"https://chatgpt.com/backend-api/hermes/agent/{self.agent_id}/conversations?{urllib.parse.urlencode(params)}"
        s, b = self._get(url)
        if s != 200:
            raise SystemExit(f"list conversations failed: HTTP {s}\n  {redact(b[:300])}")
        j = json.loads(b)
        return j.get("items", []) or [], j.get("cursor")

    def fetch_conversation(self, conv_id: str) -> dict | None:
        s, b = self._get(f"https://chatgpt.com/backend-api/conversation/{conv_id}")
        if s == 404:
            return None
        if s != 200:
            print(f"  ! fetch {conv_id}: HTTP {s} {redact(b[:160])}", file=sys.stderr)
            return None
        return json.loads(b)


def flatten_mapping(mapping: dict, current_node: str | None) -> list[dict]:
    """Order message-bearing nodes by create_time; preserve graph refs for later translation."""
    nodes = []
    for nid, node in (mapping or {}).items():
        msg = (node or {}).get("message")
        if not msg:
            continue
        author = msg.get("author") or {}
        content = msg.get("content") or {}
        nodes.append({
            "node_id": nid,
            "parent": node.get("parent"),
            "children": node.get("children") or [],
            "role": author.get("role"),
            "create_time": msg.get("create_time"),
            "content_type": content.get("content_type"),
            "parts": content.get("parts"),
            "recipient": msg.get("recipient"),
            "status": msg.get("status"),
            "metadata": msg.get("metadata"),
            "is_current": nid == current_node,
        })
    nodes.sort(key=lambda n: (n["create_time"] is None, n["create_time"] or 0))
    return nodes


def render_parts(parts) -> str:
    if not parts:
        return ""
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        else:
            out.append(json.dumps(p, ensure_ascii=False))
    return "\n".join(out)


def summarize(conv_meta: dict, msgs: list[dict]) -> str:
    roles = {}
    for m in msgs:
        roles[m["role"]] = roles.get(m["role"], 0) + 1
    lines = [
        f"# {conv_meta.get('title')}  ({conv_meta.get('conversation_id')})",
        f"   nodes={len(msgs)} roles={roles} current_node={conv_meta.get('current_node')}",
    ]
    for m in msgs:
        ct = m["create_time"]
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ct)) if isinstance(ct, (int, float)) else "?"
        head = f"   [{m['role']}] {ts} type={m['content_type']} recipient={m['recipient']}"
        if m["status"]:
            head += f" status={m['status']}"
        if m["is_current"]:
            head += " *current"
        lines.append(head)
        body = redact(render_parts(m["parts"]))
        if body:
            for ln in body.splitlines()[:6]:
                lines.append(f"     | {ln[:200]}")
        md = m.get("metadata") or {}
        if md and isinstance(md, dict):
            keys = [k for k in md.keys() if k in {"message_type", "model_slug", "tool_calls", "finish_details", "citations", "is_complete", "serialization_metadata"}]
            if keys:
                lines.append(f"     meta-keys: {keys}")
    return "\n".join(lines)


def load_seen(out_dir: Path) -> dict:
    f = out_dir / "seen.json"
    if f.is_file():
        return json.loads(f.read_text())
    return {"seen": [], "last_run": None}


def save_seen(out_dir: Path, seen: dict) -> None:
    (out_dir / "seen.json").write_text(json.dumps(seen, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="Experimental Hermes conversation poller + readback.")
    ap.add_argument("--cookie-file", default=env("HERMES_COOKIE_FILE", DEFAULTS["cookie_file"]))
    ap.add_argument("--agent", default=env("HERMES_AGENT_ID", DEFAULTS["agent_id"]))
    ap.add_argument("--account", default=env("HERMES_ACCOUNT_ID", DEFAULTS["account_id"]))
    ap.add_argument("--out-dir", default=env("HERMES_OUT_DIR", DEFAULTS["out_dir"]))
    ap.add_argument("--limit", type=int, default=20, help="conversations per list page")
    ap.add_argument("--pages", type=int, default=1, help="max list pages to walk")
    ap.add_argument("--interval", type=float, default=0, help="seconds between passes; 0 = single pass")
    ap.add_argument("--list-only", action="store_true", help="list runs, do not fetch content")
    ap.add_argument("--refetch", action="store_true", help="fetch even if already seen")
    ap.add_argument("--cf-clearance", default=os.environ.get("HERMES_CF_CLEARANCE", ""),
                    help="cf_clearance value (long-lived); appended to cookie header if jar lacks it")
    args = ap.parse_args()

    out_dir = Path(os.path.expanduser(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = load_seen(out_dir)

    def one_pass() -> None:
        if not args.agent or not args.account:
            raise SystemExit(
                "HERMES_AGENT_ID and HERMES_ACCOUNT_ID (or --agent/--account) are required; "
                "set them in .env or pass the flags."
            )
        h = Hermes(args.cookie_file, args.agent, args.account, args.cf_clearance)
        print(f"== hermes poller: agent={args.agent} limit={args.limit} pages={args.pages} list_only={args.list_only} ==")
        all_items: list[dict] = []
        cursor = None
        for _ in range(args.pages):
            items, cursor = h.list_conversations(args.limit, cursor)
            all_items.extend(items)
            if not cursor:
                break
        print(f"   listed {len(all_items)} runs")
        new_count = 0
        for it in all_items:
            cid = it.get("id")
            label = f"  - {cid}  status={it.get('fiber_status')} responding={it.get('fiber_is_responding')} inv={it.get('invocation')} title={it.get('title')!r}"
            if cid in seen["seen"] and not args.refetch:
                print(label + "  (seen)")
                continue
            print(label + "  (NEW)")
            if args.list_only:
                continue
            conv = h.fetch_conversation(cid)
            if conv is None:
                print("     ! no conversation content (404)")
                continue
            msgs = flatten_mapping(conv.get("mapping"), conv.get("current_node"))
            record = {
                "conversation_id": cid,
                "title": conv.get("title"),
                "create_time": conv.get("create_time"),
                "update_time": conv.get("update_time"),
                "async_status": conv.get("async_status"),
                "current_node": conv.get("current_node"),
                "hermes_meta": {
                    "fiber_id": it.get("fiber_id"),
                    "fiber_status": it.get("fiber_status"),
                    "fiber_is_responding": it.get("fiber_is_responding"),
                    "invocation": it.get("invocation"),
                    "last_used_at": it.get("last_used_at"),
                },
                "messages": msgs,
            }
            (out_dir / f"{cid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
            print(summarize(conv, msgs))
            if cid not in seen["seen"]:
                seen["seen"].append(cid)
            new_count += 1
        seen["last_run"] = int(time.time())
        save_seen(out_dir, seen)
        print(f"== done: {new_count} new fetched; records in {out_dir} ==")

    if args.interval <= 0:
        one_pass()
    else:
        while True:
            try:
                one_pass()
            except SystemExit as e:
                print(f"pass aborted: {e}", file=sys.stderr)
            print(f"   sleeping {args.interval}s …")
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
