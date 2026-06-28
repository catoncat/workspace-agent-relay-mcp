#!/usr/bin/env python3
"""Shared in-browser Hermes fetch client (Playwright page → chatgpt backend-api).

`PWHermes` does same-origin in-page fetch() against chatgpt.com backend-api on a
Playwright page that is already on chatgpt.com. It is transport-agnostic about how
that page was obtained:

  - hermes_poller_cdp.py attaches to a real Chrome via connect_over_cdp (the working
    path; real Chrome passes Cloudflare).
  - (hermes_poller_pw.py used to launch Playwright's own Chromium — dead end, deleted:
    Cloudflare detects Playwright Chromium even headed and loops the challenge.)

Keeping this in one place lets the CDP poller (and any future transport) reuse the
session/agents/conversations/conversation readback logic without re-implementing it.
"""
from __future__ import annotations

import base64
import json
import sys
import time


def jwt_account(token: str) -> str:
    """Extract chatgpt_account_id from a session JWT (nested in the openai-auth namespace)."""
    if not token:
        return ""
    try:
        b = token.split(".")[1].replace("-", "+").replace("_", "/")
        b += "=" * (-len(b) % 4)
        payload = json.loads(base64.b64decode(b))
        return (payload.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id", "")
    except Exception:
        return ""


class PWHermes:
    """In-page Hermes/backend-api client bound to a Playwright page on chatgpt.com."""

    def __init__(self, page) -> None:
        self.page = page
        self.jwt = ""
        self.account_id = ""

    def _fetch(self, url: str, extra_headers: dict | None = None) -> tuple[int, str]:
        headers = {"accept": "application/json"}
        if self.jwt:
            headers["authorization"] = f"Bearer {self.jwt}"
        if self.account_id:
            headers["chatgpt-account-id"] = self.account_id
        if extra_headers:
            headers.update(extra_headers)
        try:
            res = self.page.evaluate(
                """async ({url, headers}) => {
                    const r = await fetch(url, {headers, credentials: 'include'});
                    const text = await r.text();
                    return {status: r.status, body: text};
                }""",
                {"url": url, "headers": headers},
            )
        except Exception as e:
            return -1, f"eval_error:{e}"
        return res["status"], res["body"]

    def refresh_session(self) -> bool:
        s, b = self._fetch("/api/auth/session")
        if s != 200:
            return False
        try:
            j = json.loads(b)
        except Exception:
            return False
        self.jwt = j.get("accessToken", "")
        self.account_id = jwt_account(self.jwt) or (j.get("account") or {}).get("account_id", "")
        return bool(self.jwt)

    def wait_for_session(self, timeout: float = 40.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.refresh_session():
                return True
            time.sleep(2)
        return False

    def list_agents(self) -> list[dict]:
        s, b = self._fetch("/backend-api/hermes/agents")
        if s != 200:
            print(f"  ! list agents: HTTP {s} {b[:160]}", file=sys.stderr)
            return []
        j = json.loads(b)
        return j.get("items", []) or []

    def list_conversations(self, agent_id: str, limit: int, cursor: str | None = None) -> tuple[list[dict], str | None]:
        url = f"/backend-api/hermes/agent/{agent_id}/conversations?limit={limit}"
        if cursor:
            url += f"&cursor={cursor}"
        s, b = self._fetch(url)
        if s != 200:
            print(f"  ! list conversations: HTTP {s} {b[:160]}", file=sys.stderr)
            return [], None
        j = json.loads(b)
        return j.get("items", []) or [], j.get("cursor")

    def fetch_conversation(self, conv_id: str) -> dict | None:
        s, b = self._fetch(f"/backend-api/conversation/{conv_id}")
        if s == 404:
            return None
        if s != 200:
            print(f"  ! fetch {conv_id}: HTTP {s} {b[:160]}", file=sys.stderr)
            return None
        return json.loads(b)
