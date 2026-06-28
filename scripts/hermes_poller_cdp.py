#!/usr/bin/env python3
"""EXPERIMENTAL — Hermes readback via CDP-attach to YOUR real Chrome (no opencli dep).

Principle (borrowed from opencli-browser, no opencli dependency): attach Playwright to
your already-running, already-logged-in Google Chrome via the DevTools Protocol. Your
real Chrome passes Cloudflare natively (CF trusts its fingerprint), so in-page fetch()
to chatgpt.com backend-api works without any challenge, without cookie seeding, without
a separate browser window. Only Playwright is used (already installed).

Why this transport (see docs/research §9): Playwright's OWN Chromium (even headed, even with
--disable-blink-features=AutomationControlled) is detected by Cloudflare's managed
challenge on chatgpt.com — the challenge loops and never passes. Your real Chrome is not
detected, so attaching to it sidesteps the wall entirely. The shared in-page fetch client
lives in hermes_fetch.py; this script only owns the CDP-attach + poll/translate loop.

Prerequisite — Chrome must be running with the debug port + allowed origins:
  open -a "Google Chrome" --args --remote-debugging-port=9223 --remote-allow-origins=*
(9223 to avoid clashing with opencli's 9222 bridge, which is not standard CDP.)

Run:
  .venv/bin/python scripts/hermes_poller_cdp.py --list-only --limit 5

Env:
  HERMES_CDP         (default http://127.0.0.1:9223)
  HERMES_OUT_DIR      (default ~/.workspace-agent-relay-mcp/hermes-poller)
  HERMES_AGENT_ID     (optional; default: list agents, use --agent or first)

NOTE: reads whichever ChatGPT account your relay Chrome profile is logged into.
To read a different account, log that Chrome into the target account first.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hermes_poller import flatten_mapping, summarize, load_seen, save_seen  # noqa: E402
from hermes_fetch import PWHermes  # noqa: E402  (shared in-page fetch client)
from hermes_translate import events_for_store, translate_record  # noqa: E402

DEFAULT_OUT = "~/.workspace-agent-relay-mcp/hermes-poller"
DEFAULT_DB = "~/.workspace-agent-relay-mcp/relay.sqlite"
DEFAULT_RELAY = "http://127.0.0.1:8799"


def load_auth_token() -> str:
    env = os.environ.get("WORKSPACE_AGENT_RELAY_AUTH_TOKEN", "").strip()
    if env:
        return env
    for cand in (Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"):
        if cand.is_file():
            for ln in cand.read_text().splitlines():
                if ln.startswith("WORKSPACE_AGENT_RELAY_AUTH_TOKEN="):
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def post_polling_events(
    relay_url: str,
    token: str,
    run_id: int,
    events: list[dict],
    *,
    hermes_conversation_id: str | None = None,
) -> dict:
    body: dict = {
        "events": [
            {
                "source_key": e["source_key"],
                "event_type": e["event_type"],
                "title": e.get("title"),
                "markdown": e.get("markdown"),
                "payload": e.get("payload") or {},
                "create_time": e.get("create_time"),
            }
            for e in events
        ],
    }
    if hermes_conversation_id:
        body["hermes_conversation_id"] = hermes_conversation_id
    req = urllib.request.Request(
        f"{relay_url.rstrip('/')}/internal/runs/{run_id}/polling-events",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def fetch_polling_targets(relay_url: str, token: str, trigger_id: str) -> dict:
    url = f"{relay_url.rstrip('/')}/internal/polling-targets?trigger_id={urllib.parse.quote(trigger_id)}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return {"fetch_hermes_ids": [], "fast_hermes_ids": [], "discover_in_progress": True,
                "error": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"fetch_hermes_ids": [], "fast_hermes_ids": [], "discover_in_progress": True,
                "error": f"{type(e).__name__}: {e}"}


def should_fetch_conversation(cid: str, item: dict, targets: dict, *, discovery_budget: int) -> tuple[bool, str]:
    """Return (fetch?, reason_tag)."""
    fetch_set = set(targets.get("fetch_hermes_ids") or [])
    if cid in fetch_set:
        return True, "target"
    status = item.get("fiber_status")
    is_terminal = status in ("completed", "failed")
    if not is_terminal and targets.get("discover_in_progress") and discovery_budget > 0:
        return True, "discover"
    return False, "skip"


def main() -> int:
    ap = argparse.ArgumentParser(description="Experimental Hermes readback via CDP-attach to your real Chrome (no opencli dep).")
    ap.add_argument("--cdp", default=os.environ.get("HERMES_CDP", "http://127.0.0.1:9223"))
    ap.add_argument("--out-dir", default=os.environ.get("HERMES_OUT_DIR", DEFAULT_OUT))
    ap.add_argument("--db", default=os.environ.get("HERMES_DB", DEFAULT_DB),
                    help="relay sqlite path for translation correlation")
    ap.add_argument("--agent", default=os.environ.get("HERMES_AGENT_ID", ""), help="agent agt_ id; if empty, list agents and use first")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--no-translate", action="store_true", help="skip writing <cid>.events.json")
    ap.add_argument("--no-apply", action="store_true",
                    help="skip POSTing store-ready events to the relay (dry-run: only write .events.json)")
    ap.add_argument("--relay-url", default=os.environ.get("RELAY_URL", DEFAULT_RELAY),
                    help="relay base url for POSTing polling events")
    ap.add_argument("--relay-token", default="",
                    help="relay shared bearer (default: WORKSPACE_AGENT_RELAY_AUTH_TOKEN from env/.env)")
    ap.add_argument("--interval", type=float, default=0,
                    help="seconds between passes; 0 = single pass (otherwise loops until Ctrl-C)")
    ap.add_argument("--no-smart", action="store_true",
                    help="fetch every listed conversation (legacy); default uses relay polling-targets")
    ap.add_argument("--discovery-limit", type=int, default=3,
                    help="max in-progress Hermes convs to fetch per pass when binding hot unmapped runs")
    args = ap.parse_args()

    out_dir = Path(os.path.expanduser(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(os.path.expanduser(args.db))
    seen = load_seen(out_dir)
    do_translate = not args.no_translate
    do_apply = not args.no_apply
    relay_token = (args.relay_token or load_auth_token()).strip()
    if do_apply and not relay_token:
        print("  ! --no-apply not set and no WORKSPACE_AGENT_RELAY_AUTH_TOKEN found; disabling apply", file=sys.stderr)
        do_apply = False
    # Line-buffer stdout so watch-mode output is visible when redirected/backgrounded.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(args.cdp)
        except Exception as e:
            print(f"! cannot connect to CDP at {args.cdp}: {e}", file=sys.stderr)
            print('  start Chrome with: open -a "Google Chrome" --args --remote-debugging-port=9223 --remote-allow-origins=*', file=sys.stderr)
            return 4
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()

        page = None
        for c in ctx.pages:
            if "chatgpt.com" in c.url:
                page = c
                break
        created_tab = False
        if page is None:
            page = ctx.new_page()
            created_tab = True
            print("  no chatgpt.com tab open — opening one in your Chrome…")
            try:
                page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"  goto warn: {e}", file=sys.stderr)
            page.wait_for_timeout(1500)

        try:
            h = PWHermes(page)
            if not h.wait_for_session(timeout=40):
                print("  ! no session — is this Chrome logged into chatgpt.com?", file=sys.stderr)
                return 2
            print(f"  session ok: account={h.account_id} jwt_len={len(h.jwt)}")

            agent_id = args.agent
            if not agent_id:
                agents = h.list_agents()
                print(f"  agents: {[(a['id'], a.get('name')) for a in agents]}")
                if not agents:
                    print("  ! no agents visible", file=sys.stderr)
                    return 3
                agent_id = agents[0]["id"]
            print(f"  using agent={agent_id}")

            def one_pass() -> tuple[int, float]:
                # Re-check session each pass (long-running loops outlive a single JWT).
                if not h.refresh_session() and not h.wait_for_session(timeout=20):
                    print("  ! session lost mid-loop — re-login in the relay Chrome and restart", file=sys.stderr)
                    return 2, float(args.interval or 60)
                targets: dict = {}
                if not args.no_smart:
                    targets = fetch_polling_targets(args.relay_url, relay_token, agent_id)
                    if targets.get("error"):
                        print(f"  ! polling-targets: {targets['error']}", file=sys.stderr)
                    fetch_n = len(targets.get("fetch_hermes_ids") or [])
                    fast_n = len(targets.get("fast_hermes_ids") or [])
                    print(
                        f"  targets: fetch={fetch_n} fast={fast_n} "
                        f"discover={'on' if targets.get('discover_in_progress') else 'off'} "
                        f"active_convs={len(targets.get('active_conversation_ids') or [])}"
                    )
                all_items: list[dict] = []
                cursor = None
                for _ in range(args.pages):
                    items, cursor = h.list_conversations(agent_id, args.limit, cursor)
                    all_items.extend(items)
                    if not cursor:
                        break
                print(f"  listed {len(all_items)} runs")
                new_count = 0
                bound_count = 0
                skipped = 0
                discovery_left = args.discovery_limit if not args.no_smart else 0
                for it in all_items:
                    cid = it.get("id")
                    status = it.get("fiber_status")
                    tag = f"  - {cid} status={status} inv={it.get('invocation')} title={it.get('title')!r}"
                    # Re-fetch conversations that are not yet terminal even if already seen —
                    # an in-progress conversation fetched early may contain only route echoes;
                    # the agent's real replies arrive later and must be re-read. Idempotent
                    # writes (INSERT OR IGNORE on source_key) make re-fetching safe. Only
                    # terminal (completed/failed) seen conversations are skipped.
                    is_terminal = status in ("completed", "failed")
                    if cid in seen["seen"] and is_terminal and not args.refetch:
                        continue
                    if not args.no_smart:
                        smart_fetch, reason = should_fetch_conversation(
                            cid, it, targets, discovery_budget=discovery_left,
                        )
                        if not smart_fetch:
                            skipped += 1
                            continue
                        if reason == "discover":
                            discovery_left -= 1
                    else:
                        reason = "legacy"
                    suffix = ""
                    if cid in seen["seen"]:
                        suffix = "  (seen, in-progress → refetch)"
                    elif reason == "discover":
                        suffix = "  (discover)"
                    elif reason == "target":
                        suffix = "  (target)"
                    print(tag + suffix)
                    if args.list_only:
                        continue
                    conv = h.fetch_conversation(cid)
                    if conv is None:
                        continue
                    msgs = flatten_mapping(conv.get("mapping"), conv.get("current_node"))
                    record = {
                        "conversation_id": cid, "title": conv.get("title"),
                        "create_time": conv.get("create_time"), "current_node": conv.get("current_node"),
                        "hermes_meta": {"fiber_id": it.get("fiber_id"), "fiber_status": it.get("fiber_status"),
                                        "fiber_is_responding": it.get("fiber_is_responding"),
                                        "invocation": it.get("invocation"), "last_used_at": it.get("last_used_at")},
                        "messages": msgs,
                    }
                    (out_dir / f"{cid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
                    print(summarize(conv, msgs))
                    if do_translate:
                        try:
                            ev = translate_record(record, db_path)
                            (out_dir / f"{cid}.events.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2))
                            s = ev["summary"]
                            bound_count += s["bound_to_relay"]
                            print(f"     translated: turns={s['turns']} bound={s['bound_to_relay']} unbound={s['unbound']}")
                        except Exception as exc:
                            print(f"  ! translate {cid}: {exc}", file=sys.stderr)
                    if do_apply:
                        try:
                            store_events = events_for_store(record, db_path)
                            by_run: dict[int, list[dict]] = {}
                            for ev in store_events:
                                by_run.setdefault(int(ev["run_id"]), []).append(ev)
                            for run_id, evs in by_run.items():
                                res = post_polling_events(
                                    args.relay_url, relay_token, run_id, evs,
                                    hermes_conversation_id=cid,
                                )
                                if res.get("success"):
                                    print(f"     applied run={run_id}: inserted={res.get('inserted')} of {len(evs)}")
                                else:
                                    print(f"  ! apply run={run_id}: {res.get('error')}", file=sys.stderr)
                        except Exception as exc:
                            print(f"  ! apply {cid}: {exc}", file=sys.stderr)
                    # Only mark seen once the conversation reaches a terminal state —
                    # otherwise it stays re-fetchable until the agent's real replies land.
                    if is_terminal and cid not in seen["seen"]:
                        seen["seen"].append(cid)
                    new_count += 1
                seen["last_run"] = int(time.time())
                save_seen(out_dir, seen)
                sleep_sec = float(args.interval or 60)
                if not args.no_smart and targets:
                    fast = set(targets.get("fast_hermes_ids") or [])
                    active = bool(targets.get("active_conversation_ids"))
                    if active or fast:
                        sleep_sec = float(targets.get("interval_active_sec") or 5)
                    else:
                        sleep_sec = float(targets.get("interval_idle_sec") or 60)
                print(
                    f"== pass done: {new_count} fetched, {skipped} skipped (unwatched), "
                    f"{bound_count} turns bound; records in {out_dir} =="
                )
                return 0, sleep_sec

            if args.interval <= 0:
                rc, _ = one_pass()
                return rc
            print(f"== watch mode: smart={'on' if not args.no_smart else 'off'}; Ctrl-C to stop ==")
            pass_no = 0
            while True:
                pass_no += 1
                print(f"\n== pass #{pass_no} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ==")
                try:
                    rc, sleep_sec = one_pass()
                except Exception as exc:
                    print(f"  pass crashed: {exc}", file=sys.stderr)
                    rc, sleep_sec = 0, float(args.interval or 60)
                if rc == 2:
                    return 2
                print(f"   sleeping {sleep_sec}s …")
                time.sleep(sleep_sec)
        finally:
            # Intentionally do NOT close the created tab and do NOT call browser.close().
            # Closing the only tab would close the relay window and could disturb a
            # just-completed login. Keep the chatgpt.com tab open so the relay Chrome
            # stays up and the next run reuses it. browser.close() would quit your Chrome.
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
