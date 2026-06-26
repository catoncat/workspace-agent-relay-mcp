# Workspace Agent Relay MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first relay MCP and web console that triggers ChatGPT Workspace Agents and receives progress, questions, and final Markdown results back through local MCP callbacks.

**Architecture:** A Python FastMCP service exposes narrow communication tools at `/mcp`, local HTTP API routes under `/api`, and a static dashboard at `/`. SQLite stores agents, conversations, runs, events, and artifacts. Workspace Agent trigger calls include `request_id`, `conversation_key`, and a per-run `callback_token`; MCP write tools validate that token before persisting anything.

**Tech Stack:** Python 3.11+, FastMCP 3.x, uvicorn, Starlette, stdlib sqlite3/urllib, pytest, optional cloudflared for tunnel exposure.

---

## File Structure

- Create `pyproject.toml`: package metadata, runtime dependencies, pytest dependency, console script.
- Create `.gitignore`: local env, venv, caches, SQLite state, build outputs.
- Create `.env.example`: safe example configuration with no real secrets.
- Create `README.md`: setup, ChatGPT/Workspace Agent configuration, smoke test, security notes.
- Create `src/workspace_agent_relay_mcp/__init__.py`: package version.
- Create `src/workspace_agent_relay_mcp/config.py`: environment configuration and runtime directory setup.
- Create `src/workspace_agent_relay_mcp/db.py`: SQLite schema, store methods, callback validation, event/artifact persistence.
- Create `src/workspace_agent_relay_mcp/trigger.py`: request ID generation, callback token generation, trigger input contract, trigger API client.
- Create `src/workspace_agent_relay_mcp/oauth.py`: adapted OAuth compatibility from `notion-local-ops-mcp` with relay names/scopes.
- Create `src/workspace_agent_relay_mcp/http_compat.py`: adapted streamable HTTP/SSE/Bearer/OAuth compatibility from `notion-local-ops-mcp`.
- Create `src/workspace_agent_relay_mcp/server.py`: FastMCP tools, HTTP app builder, uvicorn entrypoint.
- Create `src/workspace_agent_relay_mcp/web.py`: Starlette routes for local dashboard/API/static HTML.
- Create `scripts/dev-tunnel.sh`: local server + cloudflared quick/named tunnel launcher.
- Create `tests/test_config.py`: config defaults and env overrides.
- Create `tests/test_relay_store.py`: SQLite schema and callback behavior.
- Create `tests/test_trigger_payload.py`: trigger input and HTTP client behavior without live API.
- Create `tests/test_mcp_callbacks.py`: direct MCP tool callback tests.
- Create `tests/test_server_transport.py`: HTTP auth/discovery/streamable MCP compatibility.
- Create `tests/test_web_api.py`: local API behavior with fake trigger client.

---

### Task 1: Bootstrap Package, Config, And Test Harness

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/workspace_agent_relay_mcp/__init__.py`
- Create: `src/workspace_agent_relay_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
from pathlib import Path

from workspace_agent_relay_mcp.config import RelayConfig, load_config


def test_load_config_uses_safe_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WORKSPACE_AGENT_RELAY_HOST", raising=False)
    monkeypatch.delenv("WORKSPACE_AGENT_RELAY_PORT", raising=False)
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_STATE_DIR", str(tmp_path / "state"))

    config = load_config()

    assert isinstance(config, RelayConfig)
    assert config.host == "127.0.0.1"
    assert config.port == 8799
    assert config.state_dir == tmp_path / "state"
    assert config.database_path == tmp_path / "state" / "relay.sqlite"
    assert config.auth_mode == ""
    assert config.auth_token == ""


def test_load_config_reads_env_overrides(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_HOST", "0.0.0.0")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_PORT", "8801")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_STATE_DIR", str(tmp_path / "custom-state"))
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_AUTH_TOKEN", "relay-secret")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_AGENT_TOKEN", "agent-secret")
    monkeypatch.setenv("WORKSPACE_AGENT_RELAY_TRIGGER_URL", "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger")

    config = load_config()

    assert config.host == "0.0.0.0"
    assert config.port == 8801
    assert config.state_dir == tmp_path / "custom-state"
    assert config.auth_token == "relay-secret"
    assert config.default_agent_token == "agent-secret"
    assert config.default_trigger_url.endswith("/agtch_test/trigger")


def test_ensure_runtime_directories_creates_owner_only_state_dir(tmp_path: Path) -> None:
    config = RelayConfig(state_dir=tmp_path / "state")

    config.ensure_runtime_directories()

    assert config.state_dir.is_dir()
    assert oct(config.state_dir.stat().st_mode & 0o777) == "0o700"
```

- [ ] **Step 2: Run tests and verify they fail because package does not exist**

Run:

```bash
python3 -m pytest tests/test_config.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'workspace_agent_relay_mcp'`.

- [ ] **Step 3: Add package metadata and ignores**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "workspace-agent-relay-mcp"
version = "0.1.0"
description = "Local relay MCP and dashboard for ChatGPT Workspace Agent trigger callbacks."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=3.2.4,<4",
    "uvicorn>=0.30.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
]

[project.scripts]
workspace-agent-relay-mcp = "workspace_agent_relay_mcp.server:main"

[tool.setuptools.package-dir]
"" = "src"

[tool.setuptools.packages.find]
where = ["src"]
```

Create `.gitignore`:

```gitignore
.DS_Store
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
dist/
build/
*.egg-info/
*.sqlite
*.sqlite-shm
*.sqlite-wal
cloudflared.local.yml
cloudflared.local.yaml
```

Create `.env.example`:

```bash
WORKSPACE_AGENT_RELAY_HOST=127.0.0.1
WORKSPACE_AGENT_RELAY_PORT=8799
WORKSPACE_AGENT_RELAY_STATE_DIR=~/.workspace-agent-relay-mcp
WORKSPACE_AGENT_RELAY_AUTH_TOKEN=replace-me

# OAuth mode for ChatGPT web developer mode, if needed.
# WORKSPACE_AGENT_RELAY_AUTH_MODE=oauth
# WORKSPACE_AGENT_RELAY_PUBLIC_BASE_URL=https://your-public-mcp-host.example
# WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN=replace-me-login-token
# WORKSPACE_AGENT_RELAY_OAUTH_SCOPES=workspace-agent-relay
# WORKSPACE_AGENT_RELAY_OAUTH_TOKEN_TTL_SECONDS=86400

# Optional single default Workspace Agent. Additional agents can be added via API later.
WORKSPACE_AGENT_RELAY_AGENT_NAME=default
WORKSPACE_AGENT_RELAY_TRIGGER_URL=https://api.chatgpt.com/v1/workspace_agents/agtch_replace_me/trigger
WORKSPACE_AGENT_RELAY_AGENT_TOKEN=replace-me-workspace-agent-access-token

WORKSPACE_AGENT_RELAY_DEBUG_MCP_LOGGING=0
WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG=
WORKSPACE_AGENT_RELAY_TUNNEL_NAME=
```

- [ ] **Step 4: Add package init and config implementation**

Create `src/workspace_agent_relay_mcp/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/workspace_agent_relay_mcp/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


APP_NAME = "workspace-agent-relay-mcp"
DEFAULT_SCOPE = "workspace-agent-relay"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RelayConfig:
    host: str = "127.0.0.1"
    port: int = 8799
    state_dir: Path = Path.home() / ".workspace-agent-relay-mcp"
    auth_token: str = ""
    auth_mode: str = ""
    public_base_url: str = ""
    oauth_login_token: str = ""
    oauth_scopes: tuple[str, ...] = (DEFAULT_SCOPE,)
    oauth_token_ttl_seconds: int = 86400
    debug_mcp_logging: bool = False
    default_agent_name: str = "default"
    default_trigger_url: str = ""
    default_agent_token: str = ""

    @property
    def database_path(self) -> Path:
        return self.state_dir / "relay.sqlite"

    def ensure_runtime_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.state_dir.chmod(0o700)
        except OSError:
            pass


def load_config() -> RelayConfig:
    scopes = tuple(
        scope
        for scope in os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_SCOPES", DEFAULT_SCOPE).split()
        if scope
    )
    return RelayConfig(
        host=os.environ.get("WORKSPACE_AGENT_RELAY_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(os.environ.get("WORKSPACE_AGENT_RELAY_PORT", "8799")),
        state_dir=Path(
            os.environ.get(
                "WORKSPACE_AGENT_RELAY_STATE_DIR",
                str(Path.home() / ".workspace-agent-relay-mcp"),
            )
        ).expanduser().resolve(),
        auth_token=os.environ.get("WORKSPACE_AGENT_RELAY_AUTH_TOKEN", "").strip(),
        auth_mode=os.environ.get("WORKSPACE_AGENT_RELAY_AUTH_MODE", "").strip().lower(),
        public_base_url=os.environ.get("WORKSPACE_AGENT_RELAY_PUBLIC_BASE_URL", "").strip().rstrip("/"),
        oauth_login_token=os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_LOGIN_TOKEN", "").strip(),
        oauth_scopes=scopes or (DEFAULT_SCOPE,),
        oauth_token_ttl_seconds=int(os.environ.get("WORKSPACE_AGENT_RELAY_OAUTH_TOKEN_TTL_SECONDS", "86400")),
        debug_mcp_logging=_env_flag("WORKSPACE_AGENT_RELAY_DEBUG_MCP_LOGGING", default=False),
        default_agent_name=os.environ.get("WORKSPACE_AGENT_RELAY_AGENT_NAME", "default").strip() or "default",
        default_trigger_url=os.environ.get("WORKSPACE_AGENT_RELAY_TRIGGER_URL", "").strip(),
        default_agent_token=os.environ.get("WORKSPACE_AGENT_RELAY_AGENT_TOKEN", "").strip(),
    )
```

- [ ] **Step 5: Add initial README**

Create `README.md`:

```markdown
# workspace-agent-relay-mcp

Local relay MCP and dashboard for ChatGPT Workspace Agent trigger runs.

The Workspace Agent trigger API accepts asynchronous work but does not currently provide a response retrieval API. This project gives the agent a narrow local MCP callback surface so it can write progress, questions, and final Markdown results back to your machine.

## Security model

- The Workspace Agent access token stays local.
- MCP write callbacks require a per-run `callback_token`.
- The MCP tools do not expose shell, arbitrary file reads, or arbitrary file writes.
- The first version is a communication bridge, not a local-ops server.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`, then run:

```bash
workspace-agent-relay-mcp
```

Local dashboard:

```text
http://127.0.0.1:8799/
```

MCP endpoint:

```text
http://127.0.0.1:8799/mcp
```
```

- [ ] **Step 6: Run config tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_config.py -q
```

Expected: `3 passed`.

- [ ] **Step 7: Commit bootstrap**

Run:

```bash
git add pyproject.toml .gitignore .env.example README.md src/workspace_agent_relay_mcp/__init__.py src/workspace_agent_relay_mcp/config.py tests/test_config.py
git commit -m "chore: 初始化 relay mcp 项目骨架"
```

---

### Task 2: Implement SQLite Relay Store And Callback Validation

**Files:**
- Create: `src/workspace_agent_relay_mcp/db.py`
- Create: `tests/test_relay_store.py`

- [ ] **Step 1: Write failing relay store tests**

Create `tests/test_relay_store.py`:

```python
from pathlib import Path

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
    assert "secret-callback" not in str(run)
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
    question = store.ask_user(
        request_id="run_1",
        conversation_key="research:sherlog",
        callback_token="secret-callback",
        question="Which branch?",
        choices=["main", "dev"],
        context="Need target branch",
    )
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
    store.create_run(
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

    context = store.get_run_context("research:sherlog", limit=3)

    rendered = str(context)
    assert context["success"] is True
    assert "secret-callback" not in rendered
    assert "callback_token_hash" not in rendered
    assert context["runs"][0]["request_id"] == "run_1"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_relay_store.py -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `workspace_agent_relay_mcp.db`.

- [ ] **Step 3: Implement `db.py`**

Create `src/workspace_agent_relay_mcp/db.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import hmac
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator


TERMINAL_STATUSES = {"done", "blocked", "failed"}
VALID_RESULT_STATUSES = TERMINAL_STATUSES


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _extract_trigger_id(trigger_url: str) -> str:
    match = re.search(r"/workspace_agents/([^/]+)/trigger$", trigger_url)
    return match.group(1) if match else ""


class RelayStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.database_path.parent.chmod(0o700)
        except OSError:
            pass
        self._lock = threading.RLock()
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    trigger_url TEXT NOT NULL,
                    trigger_id TEXT NOT NULL,
                    token_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    conversation_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived_at TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    conversation_key TEXT NOT NULL,
                    callback_token_hash TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    request_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT,
                    markdown TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_agent(self, *, name: str, trigger_url: str, token_ref: str) -> dict[str, Any]:
        now = _now()
        trigger_id = _extract_trigger_id(trigger_url)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents (name, trigger_url, trigger_id, token_ref, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    trigger_url = excluded.trigger_url,
                    trigger_id = excluded.trigger_id,
                    token_ref = excluded.token_ref,
                    updated_at = excluded.updated_at
                """,
                (name, trigger_url, trigger_id, token_ref, now, now),
            )
            return self.get_agent_by_name(name)

    def get_agent_by_name(self, name: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {name}")
        return _row_to_dict(row) or {}

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def create_conversation(self, *, agent_id: int, name: str, conversation_key: str) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (agent_id, name, conversation_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, name, conversation_key, now, now),
            )
            row = conn.execute("SELECT * FROM conversations WHERE conversation_key = ?", (conversation_key,)).fetchone()
        return _row_to_dict(row) or {}

    def list_conversations(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM conversations WHERE archived_at IS NULL ORDER BY updated_at DESC").fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def get_conversation(self, conversation_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        return _row_to_dict(row) or {}

    def create_run(
        self,
        *,
        agent_id: int,
        conversation_id: int,
        conversation_key: str,
        input_markdown: str,
        callback_token: str,
        idempotency_key: str,
        request_id: str,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    request_id, agent_id, conversation_id, conversation_key, callback_token_hash,
                    idempotency_key, input_markdown, status, trigger_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', 'draft', ?, ?)
                """,
                (
                    request_id,
                    agent_id,
                    conversation_id,
                    conversation_key,
                    _hash_token(callback_token),
                    idempotency_key,
                    input_markdown,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        payload = _row_to_dict(row) or {}
        payload.pop("callback_token_hash", None)
        return payload

    def get_run_by_request_id(self, request_id: str, *, include_secret_hash: bool = False) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {request_id}")
        payload = _row_to_dict(row) or {}
        if not include_secret_hash:
            payload.pop("callback_token_hash", None)
        return payload

    def update_run_trigger_result(
        self,
        *,
        request_id: str,
        trigger_http_status: int,
        trigger_x_request_id: str | None,
        conversation_url: str | None,
    ) -> dict[str, Any]:
        status = "accepted" if 200 <= trigger_http_status < 300 else "failed"
        trigger_status = "accepted" if status == "accepted" else "failed"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, trigger_status = ?, trigger_http_status = ?,
                    trigger_x_request_id = ?, conversation_url = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status, trigger_status, trigger_http_status, trigger_x_request_id, conversation_url, now, request_id),
            )
        return self.get_run_by_request_id(request_id)

    def validate_callback(self, request_id: str, conversation_key: str, callback_token: str) -> dict[str, Any]:
        try:
            run = self.get_run_by_request_id(request_id, include_secret_hash=True)
        except KeyError:
            return {"success": False, "error": {"code": "run_not_found", "message": "Run was not found."}}
        if run["conversation_key"] != conversation_key:
            return {"success": False, "error": {"code": "conversation_mismatch", "message": "conversation_key does not match run."}}
        if run["status"] in TERMINAL_STATUSES:
            return {"success": False, "error": {"code": "run_closed", "message": "Run is already terminal."}}
        expected = str(run["callback_token_hash"])
        actual = _hash_token(callback_token)
        if not hmac.compare_digest(expected, actual):
            return {"success": False, "error": {"code": "invalid_callback_token", "message": "callback_token is invalid."}}
        run.pop("callback_token_hash", None)
        return {"success": True, "run": run}

    def _append_event(
        self,
        *,
        run_id: int,
        request_id: str,
        event_type: str,
        title: str | None,
        markdown: str | None,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events (run_id, request_id, event_type, title, markdown, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, request_id, event_type, title, markdown, _json_dumps(payload or {}), now),
            )
            row = conn.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row) or {}

    def record_progress(
        self,
        *,
        request_id: str,
        conversation_key: str,
        callback_token: str,
        message: str,
        title: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validation = self.validate_callback(request_id, conversation_key, callback_token)
        if not validation["success"]:
            return validation
        run = validation["run"]
        event = self._append_event(
            run_id=int(run["id"]),
            request_id=request_id,
            event_type="progress",
            title=title,
            markdown=message,
            payload=payload,
        )
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE runs SET status = 'waiting', updated_at = ? WHERE id = ?", (_now(), run["id"]))
        return {"success": True, "event_id": event["id"]}

    def ask_user(
        self,
        *,
        request_id: str,
        conversation_key: str,
        callback_token: str,
        question: str,
        choices: list[str] | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        validation = self.validate_callback(request_id, conversation_key, callback_token)
        if not validation["success"]:
            return validation
        run = validation["run"]
        event = self._append_event(
            run_id=int(run["id"]),
            request_id=request_id,
            event_type="question",
            title="User input needed",
            markdown=question,
            payload={"choices": choices or [], "context": context or ""},
        )
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE runs SET status = 'needs_user', updated_at = ? WHERE id = ?", (_now(), run["id"]))
        return {"success": True, "event_id": event["id"], "question_id": event["id"]}

    def record_result(
        self,
        *,
        request_id: str,
        conversation_key: str,
        callback_token: str,
        status: str,
        title: str,
        markdown: str,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if status not in VALID_RESULT_STATUSES:
            return {"success": False, "error": {"code": "invalid_status", "message": "status must be done, blocked, or failed."}}
        validation = self.validate_callback(request_id, conversation_key, callback_token)
        if not validation["success"]:
            return validation
        run = validation["run"]
        self._append_event(
            run_id=int(run["id"]),
            request_id=request_id,
            event_type="result",
            title=title,
            markdown=markdown,
            payload={"status": status},
        )
        now = _now()
        with self._lock, self._connect() as conn:
            for artifact in artifacts or []:
                conn.execute(
                    """
                    INSERT INTO artifacts (run_id, name, mime_type, content, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run["id"],
                        str(artifact.get("name") or "artifact.txt"),
                        str(artifact.get("mime_type") or "text/plain"),
                        str(artifact.get("content") or ""),
                        _json_dumps(artifact.get("metadata") or {}),
                        now,
                    ),
                )
            conn.execute(
                "UPDATE runs SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (status, now, now, run["id"]),
            )
        return {"success": True, "run_status": status}

    def list_events(self, run_id: int) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def list_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def list_runs_for_conversation(self, conversation_id: int) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM runs WHERE conversation_id = ? ORDER BY id DESC", (conversation_id,)).fetchall()
        runs = []
        for row in rows:
            payload = _row_to_dict(row) or {}
            payload.pop("callback_token_hash", None)
            runs.append(payload)
        return runs

    def get_run_context(self, conversation_key: str, limit: int = 5) -> dict[str, Any]:
        capped_limit = max(1, min(int(limit), 20))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, request_id, status, input_markdown, conversation_url, created_at, completed_at
                FROM runs
                WHERE conversation_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_key, capped_limit),
            ).fetchall()
        runs = []
        for row in rows:
            run = _row_to_dict(row) or {}
            events = self.list_events(int(run["id"]))
            run["events"] = [
                {
                    "event_type": event["event_type"],
                    "title": event["title"],
                    "markdown": (event["markdown"] or "")[:4000],
                    "created_at": event["created_at"],
                }
                for event in events[-5:]
            ]
            runs.append(run)
        return {"success": True, "conversation_key": conversation_key, "runs": runs}
```

- [ ] **Step 4: Run relay store tests and verify they pass**

Run:

```bash
python3 -m pytest tests/test_relay_store.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Run all current tests**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit store implementation**

Run:

```bash
git add src/workspace_agent_relay_mcp/db.py tests/test_relay_store.py
git commit -m "feat(store): 增加 relay sqlite 状态库"
```

---

### Task 3: Implement Trigger Payload Builder And Workspace Agent HTTP Client

**Files:**
- Create: `src/workspace_agent_relay_mcp/trigger.py`
- Create: `tests/test_trigger_payload.py`

- [ ] **Step 1: Write failing trigger tests**

Create `tests/test_trigger_payload.py`:

```python
import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from workspace_agent_relay_mcp.trigger import (
    TriggerClient,
    build_trigger_input,
    generate_callback_token,
    generate_request_id,
)


def test_generate_ids_are_prefixed_and_distinct() -> None:
    first = generate_request_id("relay")
    second = generate_request_id("relay")
    token = generate_callback_token()

    assert first.startswith("relay_")
    assert second.startswith("relay_")
    assert first != second
    assert len(token) >= 32


def test_build_trigger_input_contains_callback_contract() -> None:
    rendered = build_trigger_input(
        request_id="relay_123",
        conversation_key="research:sherlog",
        callback_token="callback-secret",
        user_input="Please research sherlog.",
    )

    assert "request_id: relay_123" in rendered
    assert "conversation_key: research:sherlog" in rendered
    assert "callback_token: callback-secret" in rendered
    assert "record_result" in rendered
    assert "Do not only answer in the ChatGPT conversation." in rendered
    assert rendered.endswith("Please research sherlog.")


class FakeResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status = status
        self._body = body
        self.headers = headers

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class FakeOpener:
    def __init__(self) -> None:
        self.request: Request | None = None

    def open(self, request: Request, timeout: float):
        self.request = request
        return FakeResponse(
            202,
            b'{"conversation_url":"https://chatgpt.com/c/test"}',
            {"x-request-id": "req_api_123"},
        )


def test_trigger_client_posts_expected_payload() -> None:
    opener = FakeOpener()
    client = TriggerClient(opener=opener)

    result = client.trigger(
        trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
        access_token="agent-token",
        conversation_key="research:sherlog",
        input_text="hello",
        idempotency_key="relay_123",
    )

    assert result.http_status == 202
    assert result.x_request_id == "req_api_123"
    assert result.conversation_url == "https://chatgpt.com/c/test"
    assert opener.request is not None
    assert opener.request.get_method() == "POST"
    assert opener.request.headers["Authorization"] == "Bearer agent-token"
    assert opener.request.headers["Idempotency-key"] == "relay_123"
    body = json.loads(opener.request.data.decode("utf-8"))
    assert body == {"conversation_key": "research:sherlog", "input": "hello"}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_trigger_payload.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `workspace_agent_relay_mcp.trigger`.

- [ ] **Step 3: Implement trigger module**

Create `src/workspace_agent_relay_mcp/trigger.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener


def generate_request_id(prefix: str = "relay") -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{prefix}_{stamp}_{secrets.token_hex(6)}"


def generate_callback_token() -> str:
    return secrets.token_urlsafe(32)


def build_trigger_input(
    *,
    request_id: str,
    conversation_key: str,
    callback_token: str,
    user_input: str,
) -> str:
    return "\n".join(
        [
            f"request_id: {request_id}",
            f"conversation_key: {conversation_key}",
            f"callback_token: {callback_token}",
            "relay_mcp: workspace-agent-relay-mcp",
            "",
            "Completion contract:",
            "Before you finish, call workspace-agent-relay-mcp.record_result with the exact request_id, conversation_key, callback_token, status, title, and full Markdown result.",
            "Use workspace-agent-relay-mcp.record_progress for meaningful progress updates.",
            "Use workspace-agent-relay-mcp.ask_user if you are blocked on a user decision.",
            "Do not only answer in the ChatGPT conversation.",
            "",
            "User task:",
            user_input.strip(),
        ]
    )


@dataclass(frozen=True)
class TriggerResult:
    http_status: int
    x_request_id: str | None
    conversation_url: str | None
    response_body: dict[str, Any]
    error: str | None = None

    @property
    def accepted(self) -> bool:
        return 200 <= self.http_status < 300


class TriggerClient:
    def __init__(self, *, opener: Any | None = None, timeout: float = 60.0) -> None:
        self.opener = opener or build_opener()
        self.timeout = timeout

    def trigger(
        self,
        *,
        trigger_url: str,
        access_token: str,
        conversation_key: str,
        input_text: str,
        idempotency_key: str,
    ) -> TriggerResult:
        payload = {"conversation_key": conversation_key, "input": input_text}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            trigger_url,
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw.strip() else {}
                return TriggerResult(
                    http_status=int(response.status),
                    x_request_id=response.headers.get("x-request-id"),
                    conversation_url=parsed.get("conversation_url") if isinstance(parsed, dict) else None,
                    response_body=parsed if isinstance(parsed, dict) else {},
                )
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return TriggerResult(
                http_status=int(exc.code),
                x_request_id=exc.headers.get("x-request-id"),
                conversation_url=None,
                response_body=parsed if isinstance(parsed, dict) else {},
                error=str(parsed),
            )
        except URLError as exc:
            return TriggerResult(
                http_status=0,
                x_request_id=None,
                conversation_url=None,
                response_body={},
                error=str(exc.reason),
            )
```

- [ ] **Step 4: Run trigger tests**

Run:

```bash
python3 -m pytest tests/test_trigger_payload.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run all current tests**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit trigger implementation**

Run:

```bash
git add src/workspace_agent_relay_mcp/trigger.py tests/test_trigger_payload.py
git commit -m "feat(trigger): 构建 workspace agent 触发请求"
```

---

### Task 4: Add FastMCP Callback Tools

**Files:**
- Create: `src/workspace_agent_relay_mcp/server.py`
- Create: `tests/test_mcp_callbacks.py`

- [ ] **Step 1: Write failing direct tool tests**

Create `tests/test_mcp_callbacks.py`:

```python
import asyncio
from pathlib import Path

from workspace_agent_relay_mcp.db import RelayStore


def _call(tool, *args, **kwargs):
    fn = tool.fn if hasattr(tool, "fn") else tool
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


def _seed_run(store: RelayStore) -> None:
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


def test_record_result_tool_persists_final_markdown(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    result = _call(
        server.record_result,
        request_id="run_1",
        callback_token="secret-callback",
        conversation_key="research:sherlog",
        status="done",
        title="Final",
        markdown="Full answer",
        artifacts=[],
    )
    run = store.get_run_by_request_id("run_1")

    assert result["success"] is True
    assert run["status"] == "done"
    assert store.list_events(run["id"])[0]["markdown"] == "Full answer"


def test_record_progress_rejects_wrong_callback_token(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    store = RelayStore(tmp_path / "relay.sqlite")
    _seed_run(store)
    monkeypatch.setattr(server, "store", store)

    result = _call(
        server.record_progress,
        request_id="run_1",
        callback_token="wrong",
        conversation_key="research:sherlog",
        message="Working",
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_callback_token"


def test_server_info_lists_relay_tools(tmp_path: Path, monkeypatch) -> None:
    from workspace_agent_relay_mcp import server

    monkeypatch.setattr(server, "store", RelayStore(tmp_path / "relay.sqlite"))
    result = _call(server.server_info)

    assert result["success"] is True
    assert "record_result" in result["tools"]
    assert "record_progress" in result["tools"]
    assert "ask_user" in result["tools"]
    assert "get_run_context" in result["tools"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_mcp_callbacks.py -q
```

Expected: FAIL because `workspace_agent_relay_mcp.server` does not exist.

- [ ] **Step 3: Implement FastMCP server tools**

Create `src/workspace_agent_relay_mcp/server.py`:

```python
from __future__ import annotations

import argparse
from typing import Any

from fastmcp import FastMCP
import uvicorn

from . import __version__
from .config import APP_NAME, RelayConfig, load_config
from .db import RelayStore


config: RelayConfig = load_config()
store = RelayStore(config.database_path)

READ_ONLY_TOOL = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

LOCAL_STATE_TOOL = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

MCP_INSTRUCTIONS = (
    "This server is a narrow callback relay for Workspace Agent runs. "
    "Use record_progress for meaningful progress, ask_user when blocked on a human decision, "
    "and record_result before finishing. Do not expect shell, filesystem, or git tools here."
)

mcp = FastMCP(APP_NAME, instructions=MCP_INSTRUCTIONS)


async def _tool_names() -> list[str]:
    list_tools = getattr(mcp, "_list_tools")
    try:
        registered = await list_tools()
    except TypeError:
        registered = await list_tools(None)
    return sorted(tool.name for tool in registered)


@mcp.tool(
    name="server_info",
    title="Server Info",
    annotations=READ_ONLY_TOOL,
    description="Return relay server metadata, state path, auth mode, version, and registered tool names.",
)
async def server_info() -> dict[str, Any]:
    return {
        "success": True,
        "app_name": APP_NAME,
        "version": __version__,
        "state_dir": str(config.state_dir),
        "database_path": str(config.database_path),
        "auth": config.auth_mode or ("shared_token" if config.auth_token else "none"),
        "tools": await _tool_names(),
    }


@mcp.tool(
    name="record_progress",
    title="Record Progress",
    annotations=LOCAL_STATE_TOOL,
    description="Record a progress update for an open relay run. Requires request_id, conversation_key, and callback_token.",
)
def record_progress(
    request_id: str,
    callback_token: str,
    conversation_key: str,
    message: str,
    title: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return store.record_progress(
        request_id=request_id,
        conversation_key=conversation_key,
        callback_token=callback_token,
        message=message,
        title=title,
        payload=payload,
    )


@mcp.tool(
    name="record_result",
    title="Record Result",
    annotations=LOCAL_STATE_TOOL,
    description="Record the final Markdown result for an open relay run. This should be called before the agent finishes.",
)
def record_result(
    request_id: str,
    callback_token: str,
    conversation_key: str,
    status: str,
    title: str,
    markdown: str,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return store.record_result(
        request_id=request_id,
        conversation_key=conversation_key,
        callback_token=callback_token,
        status=status,
        title=title,
        markdown=markdown,
        artifacts=artifacts,
    )


@mcp.tool(
    name="ask_user",
    title="Ask User",
    annotations=LOCAL_STATE_TOOL,
    description="Record a question that the local user must answer before the run can continue.",
)
def ask_user(
    request_id: str,
    callback_token: str,
    conversation_key: str,
    question: str,
    choices: list[str] | None = None,
    context: str | None = None,
) -> dict[str, Any]:
    return store.ask_user(
        request_id=request_id,
        conversation_key=conversation_key,
        callback_token=callback_token,
        question=question,
        choices=choices,
        context=context,
    )


@mcp.tool(
    name="get_run_context",
    title="Get Run Context",
    annotations=READ_ONLY_TOOL,
    description="Return recent run summaries for a conversation_key. Does not return secrets or callback tokens.",
)
def get_run_context(conversation_key: str, limit: int = 5) -> dict[str, Any]:
    return store.get_run_context(conversation_key, limit=limit)


def build_http_app():
    from .web import build_app

    return build_app(mcp=mcp, store=store, config=config)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Workspace Agent Relay MCP server.")
    parser.parse_args(argv)
    config.ensure_runtime_directories()
    app = build_http_app()
    uvicorn.run(app, host=config.host, port=config.port)
```

- [ ] **Step 4: Add temporary minimal web app shim so import succeeds**

Create `src/workspace_agent_relay_mcp/web.py` with temporary app builder:

```python
from __future__ import annotations

from typing import Any


def build_app(*, mcp: Any, store: Any, config: Any):
    return mcp.http_app(path="/mcp", transport="streamable-http")
```

This file is expanded in Task 6. It exists now so `build_http_app()` is importable.

- [ ] **Step 5: Run direct MCP callback tests**

Run:

```bash
python3 -m pytest tests/test_mcp_callbacks.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Run all current tests**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit MCP tools**

Run:

```bash
git add src/workspace_agent_relay_mcp/server.py src/workspace_agent_relay_mcp/web.py tests/test_mcp_callbacks.py
git commit -m "feat(mcp): 增加 agent 回调工具"
```

---

### Task 5: Add HTTP Compatibility, Bearer Auth, And OAuth Metadata

**Files:**
- Create: `src/workspace_agent_relay_mcp/oauth.py`
- Create: `src/workspace_agent_relay_mcp/http_compat.py`
- Modify: `src/workspace_agent_relay_mcp/server.py`
- Modify: `src/workspace_agent_relay_mcp/web.py`
- Create: `tests/test_server_transport.py`

- [ ] **Step 1: Write transport/auth tests**

Create `tests/test_server_transport.py`:

```python
from pathlib import Path

from starlette.testclient import TestClient

from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore


def _client(tmp_path: Path, *, auth_token: str = "") -> TestClient:
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(state_dir=tmp_path / "state", auth_token=auth_token)
    server.store = RelayStore(server.config.database_path)
    return TestClient(server.build_http_app())


def test_server_card_is_public_and_describes_mcp_endpoint(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="secret") as client:
        response = client.get("/.well-known/mcp.json")

    assert response.status_code == 200
    body = response.json()
    assert body["transport"] == {"type": "streamable-http", "endpoint": "/mcp"}
    assert body["authentication"] == {"required": True, "schemes": ["bearer"]}
    assert body["serverInfo"]["name"] == "workspace-agent-relay-mcp"


def test_mcp_requires_bearer_when_auth_token_is_set(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="secret") as client:
        missing = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        allowed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 401
    assert allowed.status_code != 401


def test_head_and_options_are_allowed_without_auth(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="secret") as client:
        head = client.head("/mcp")
        options = client.options("/mcp")

    assert head.status_code == 204
    assert options.status_code == 204


def test_plain_get_mcp_returns_server_card_when_auth_disabled(tmp_path: Path) -> None:
    with _client(tmp_path, auth_token="") as client:
        response = client.get("/mcp", headers={"Accept": "*/*"})

    assert response.status_code == 200
    assert response.json()["transport"]["endpoint"] == "/mcp"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_server_transport.py -q
```

Expected: FAIL because `web.py` still returns raw FastMCP app without compatibility/auth.

- [ ] **Step 3: Adapt OAuth compatibility module**

Copy `../notion-local-ops-mcp/src/notion_local_ops_mcp/oauth.py` to `src/workspace_agent_relay_mcp/oauth.py`, then apply these exact changes:

```text
Replace DEFAULT_SCOPE = "local-ops" with DEFAULT_SCOPE = "workspace-agent-relay".
Replace every user-facing "notion-local-ops-mcp" string with "workspace-agent-relay-mcp".
Keep dynamic client registration, PKCE, token store permissions, and token verification behavior unchanged.
```

After the copy, run:

```bash
python3 -m py_compile src/workspace_agent_relay_mcp/oauth.py
```

Expected: no output and exit 0.

- [ ] **Step 4: Adapt HTTP compatibility module**

Copy `../notion-local-ops-mcp/src/notion_local_ops_mcp/http_compat.py` to `src/workspace_agent_relay_mcp/http_compat.py`, then apply these exact changes:

```text
Replace import ".oauth" target with "from .oauth import OAuthManager, OAuthRuntimeConfig".
Replace server card description with "Local MCP relay for ChatGPT Workspace Agent callbacks."
Replace debug logger name "notion_local_ops_mcp.mcp_debug" with "workspace_agent_relay_mcp.mcp_debug".
Keep HTTPBearerAuthMiddleware, MCPCompatibilityDispatcher, streamable HTTP routing, legacy SSE fallback, OAuth discovery routes, and debug logging behavior.
```

After the copy, run:

```bash
python3 -m py_compile src/workspace_agent_relay_mcp/http_compat.py
```

Expected: no output and exit 0.

- [ ] **Step 5: Update `server.py` and `web.py` to use compatibility app**

In `src/workspace_agent_relay_mcp/server.py`, add imports:

```python
from .oauth import OAuthRuntimeConfig
```

Add functions near the config globals:

```python
def _current_auth_token() -> str:
    return globals().get("config", config).auth_token


def _current_debug_mcp_logging() -> bool:
    return bool(globals().get("config", config).debug_mcp_logging)


def _current_oauth_config() -> OAuthRuntimeConfig:
    active = globals().get("config", config)
    return OAuthRuntimeConfig(
        auth_mode=active.auth_mode,
        auth_token=active.auth_token,
        public_base_url=active.public_base_url,
        state_dir=active.state_dir,
        oauth_login_token=active.oauth_login_token,
        oauth_scopes=active.oauth_scopes,
        oauth_token_ttl_seconds=active.oauth_token_ttl_seconds,
    )
```

Replace `build_http_app()` with:

```python
def build_http_app():
    from .web import build_app

    streamable_app = mcp.http_app(path="/mcp", transport="streamable-http")
    legacy_sse_app = mcp.http_app(path="/mcp", transport="sse")
    return build_app(
        mcp=mcp,
        streamable_app=streamable_app,
        legacy_sse_app=legacy_sse_app,
        store=store,
        config=config,
        get_auth_token=_current_auth_token,
        get_oauth_config=_current_oauth_config,
        get_debug_enabled=_current_debug_mcp_logging,
        instructions=MCP_INSTRUCTIONS,
    )
```

Replace `src/workspace_agent_relay_mcp/web.py` with:

```python
from __future__ import annotations

from typing import Any, Callable

from starlette.applications import Starlette
from starlette.routing import Mount

from .http_compat import build_http_compat_app


def build_app(
    *,
    mcp: Any,
    streamable_app: Any,
    legacy_sse_app: Any,
    store: Any,
    config: Any,
    get_auth_token: Callable[[], str],
    get_oauth_config: Callable[[], Any],
    get_debug_enabled: Callable[[], bool],
    instructions: str,
) -> Starlette:
    return build_http_compat_app(
        streamable_app=streamable_app,
        legacy_sse_app=legacy_sse_app,
        app_name="workspace-agent-relay-mcp",
        mcp_path="/mcp",
        get_auth_token=get_auth_token,
        get_oauth_config=get_oauth_config,
        get_debug_enabled=get_debug_enabled,
        instructions=instructions,
    )
```

- [ ] **Step 6: Run transport tests**

Run:

```bash
python3 -m pytest tests/test_server_transport.py -q
```

Expected: `4 passed`.

- [ ] **Step 7: Run all current tests**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit transport compatibility**

Run:

```bash
git add src/workspace_agent_relay_mcp/oauth.py src/workspace_agent_relay_mcp/http_compat.py src/workspace_agent_relay_mcp/server.py src/workspace_agent_relay_mcp/web.py tests/test_server_transport.py
git commit -m "feat(transport): 增加 mcp http 兼容与认证"
```

---

### Task 6: Add Local HTTP API For Agents, Conversations, Runs, And Follow-Ups

**Files:**
- Modify: `src/workspace_agent_relay_mcp/db.py`
- Modify: `src/workspace_agent_relay_mcp/web.py`
- Create: `tests/test_web_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_web_api.py`:

```python
from pathlib import Path

from starlette.testclient import TestClient

from workspace_agent_relay_mcp.config import RelayConfig
from workspace_agent_relay_mcp.db import RelayStore
from workspace_agent_relay_mcp.trigger import TriggerResult


class FakeTriggerClient:
    def trigger(self, **kwargs):
        return TriggerResult(
            http_status=202,
            x_request_id="api_req_123",
            conversation_url="https://chatgpt.com/c/test",
            response_body={"conversation_url": "https://chatgpt.com/c/test"},
        )


def _client(tmp_path: Path) -> TestClient:
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(
        state_dir=tmp_path / "state",
        default_agent_token="agent-token",
        default_trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
    )
    server.store = RelayStore(server.config.database_path)
    app = server.build_http_app()
    app.state.trigger_client = FakeTriggerClient()
    return TestClient(app)


def test_api_can_create_agent_and_conversation(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        agent_response = client.post(
            "/api/agents",
            json={
                "name": "default",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
                "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
            },
        )
        conversation_response = client.post(
            "/api/conversations",
            json={"agent_id": agent_response.json()["id"], "name": "Sherlog", "conversation_key": "research:sherlog"},
        )

    assert agent_response.status_code == 200
    assert agent_response.json()["trigger_id"] == "agtch_test"
    assert conversation_response.status_code == 200
    assert conversation_response.json()["conversation_key"] == "research:sherlog"


def test_api_send_run_triggers_agent_and_records_metadata(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        agent = client.post(
            "/api/agents",
            json={
                "name": "default",
                "trigger_url": "https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger",
                "token_ref": "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN",
            },
        ).json()
        conversation = client.post(
            "/api/conversations",
            json={"agent_id": agent["id"], "name": "Sherlog", "conversation_key": "research:sherlog"},
        ).json()
        run_response = client.post(
            f"/api/conversations/{conversation['id']}/runs",
            json={"input_markdown": "Research sherlog"},
        )
        runs_response = client.get(f"/api/conversations/{conversation['id']}/runs")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "accepted"
    assert run["trigger_http_status"] == 202
    assert run["trigger_x_request_id"] == "api_req_123"
    assert run["conversation_url"] == "https://chatgpt.com/c/test"
    assert runs_response.json()[0]["request_id"] == run["request_id"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m pytest tests/test_web_api.py -q
```

Expected: FAIL with 404 responses for `/api/*`.

- [ ] **Step 3: Add missing DB helper for API run retrieval**

In `src/workspace_agent_relay_mcp/db.py`, add this method to `RelayStore`:

```python
    def get_run(self, run_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        payload = _row_to_dict(row) or {}
        payload.pop("callback_token_hash", None)
        return payload
```

- [ ] **Step 4: Implement API routes in `web.py`**

Replace `src/workspace_agent_relay_mcp/web.py` with:

```python
from __future__ import annotations

from typing import Any, Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from .http_compat import build_http_compat_app
from .trigger import TriggerClient, build_trigger_input, generate_callback_token, generate_request_id


def _json_error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": message}, status_code=status_code)


def _agent_token(config: Any, token_ref: str) -> str:
    if token_ref == "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN":
        return config.default_agent_token
    return config.default_agent_token


async def _json(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return payload if isinstance(payload, dict) else {}


def _dashboard_html() -> str:
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Workspace Agent Relay</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; color: #172026; background: #f6f8fa; }
      main { display: grid; grid-template-columns: 280px 1fr 320px; min-height: 100vh; }
      aside, section { padding: 16px; border-right: 1px solid #d8dee4; }
      textarea { width: 100%; min-height: 160px; font: 14px ui-monospace, monospace; }
      input, button { font: inherit; }
      button { padding: 8px 12px; border: 1px solid #8c959f; background: white; cursor: pointer; }
      pre { white-space: pre-wrap; background: white; border: 1px solid #d8dee4; padding: 12px; }
      .run { border: 1px solid #d8dee4; background: white; margin: 8px 0; padding: 8px; }
    </style>
  </head>
  <body>
    <main>
      <aside>
        <h2>Conversations</h2>
        <button onclick="bootstrap()">Load</button>
        <div id="conversations"></div>
      </aside>
      <section>
        <h1>Workspace Agent Relay</h1>
        <label>Task</label>
        <textarea id="task"></textarea>
        <p><button onclick="sendRun()">Send</button></p>
        <h2>Runs</h2>
        <div id="runs"></div>
      </section>
      <aside>
        <h2>Details</h2>
        <pre id="details">No run selected.</pre>
      </aside>
    </main>
    <script>
      let selectedConversationId = null;
      async function api(path, options = {}) {
        const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      }
      async function bootstrap() {
        let agents = await api('/api/agents');
        if (agents.length === 0) {
          await api('/api/agents', { method: 'POST', body: JSON.stringify({ name: 'default', trigger_url: '', token_ref: 'env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN' }) });
          agents = await api('/api/agents');
        }
        let conversations = await api('/api/conversations');
        if (conversations.length === 0) {
          const key = 'default:' + new Date().toISOString().slice(0, 10);
          await api('/api/conversations', { method: 'POST', body: JSON.stringify({ agent_id: agents[0].id, name: 'Default', conversation_key: key }) });
          conversations = await api('/api/conversations');
        }
        document.getElementById('conversations').innerHTML = conversations.map(c => `<div><button onclick="selectConversation(${c.id})">${c.name}<br><small>${c.conversation_key}</small></button></div>`).join('');
        selectedConversationId = conversations[0].id;
        await loadRuns();
      }
      async function selectConversation(id) {
        selectedConversationId = id;
        await loadRuns();
      }
      async function loadRuns() {
        if (!selectedConversationId) return;
        const runs = await api(`/api/conversations/${selectedConversationId}/runs`);
        document.getElementById('runs').innerHTML = runs.map(r => `<div class="run"><button onclick='showRun(${JSON.stringify(r)})'>${r.request_id}</button><br>Status: ${r.status}</div>`).join('');
      }
      function showRun(run) {
        document.getElementById('details').textContent = JSON.stringify(run, null, 2);
      }
      async function sendRun() {
        if (!selectedConversationId) await bootstrap();
        const input = document.getElementById('task').value;
        const run = await api(`/api/conversations/${selectedConversationId}/runs`, { method: 'POST', body: JSON.stringify({ input_markdown: input }) });
        showRun(run);
        await loadRuns();
      }
      bootstrap().catch(err => document.getElementById('details').textContent = String(err));
      setInterval(loadRuns, 2000);
    </script>
  </body>
</html>
""".strip()


def build_app(
    *,
    mcp: Any,
    streamable_app: Any,
    legacy_sse_app: Any,
    store: Any,
    config: Any,
    get_auth_token: Callable[[], str],
    get_oauth_config: Callable[[], Any],
    get_debug_enabled: Callable[[], bool],
    instructions: str,
) -> Starlette:
    mcp_app = build_http_compat_app(
        streamable_app=streamable_app,
        legacy_sse_app=legacy_sse_app,
        app_name="workspace-agent-relay-mcp",
        mcp_path="/mcp",
        get_auth_token=get_auth_token,
        get_oauth_config=get_oauth_config,
        get_debug_enabled=get_debug_enabled,
        instructions=instructions,
    )

    async def dashboard(_: Request) -> HTMLResponse:
        return HTMLResponse(_dashboard_html())

    async def list_agents(_: Request) -> JSONResponse:
        return JSONResponse(store.list_agents())

    async def create_agent(request: Request) -> JSONResponse:
        payload = await _json(request)
        trigger_url = str(payload.get("trigger_url") or config.default_trigger_url)
        if not trigger_url:
            return _json_error("trigger_url is required")
        agent = store.upsert_agent(
            name=str(payload.get("name") or config.default_agent_name),
            trigger_url=trigger_url,
            token_ref=str(payload.get("token_ref") or "env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN"),
        )
        return JSONResponse(agent)

    async def list_conversations(_: Request) -> JSONResponse:
        return JSONResponse(store.list_conversations())

    async def create_conversation(request: Request) -> JSONResponse:
        payload = await _json(request)
        conversation = store.create_conversation(
            agent_id=int(payload["agent_id"]),
            name=str(payload["name"]),
            conversation_key=str(payload["conversation_key"]),
        )
        return JSONResponse(conversation)

    async def list_runs(request: Request) -> JSONResponse:
        conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        return JSONResponse(store.list_runs_for_conversation(int(conversation["id"])))

    async def create_run(request: Request) -> JSONResponse:
        payload = await _json(request)
        conversation = store.get_conversation(int(request.path_params["conversation_id"]))
        agents = store.list_agents()
        agent = next(item for item in agents if int(item["id"]) == int(conversation["agent_id"]))
        request_id = generate_request_id()
        callback_token = generate_callback_token()
        input_markdown = str(payload.get("input_markdown") or "")
        trigger_input = build_trigger_input(
            request_id=request_id,
            conversation_key=str(conversation["conversation_key"]),
            callback_token=callback_token,
            user_input=input_markdown,
        )
        store.create_run(
            agent_id=int(agent["id"]),
            conversation_id=int(conversation["id"]),
            conversation_key=str(conversation["conversation_key"]),
            input_markdown=input_markdown,
            callback_token=callback_token,
            idempotency_key=request_id,
            request_id=request_id,
        )
        trigger_client = getattr(request.app.state, "trigger_client", TriggerClient())
        trigger_result = trigger_client.trigger(
            trigger_url=str(agent["trigger_url"]),
            access_token=_agent_token(config, str(agent["token_ref"])),
            conversation_key=str(conversation["conversation_key"]),
            input_text=trigger_input,
            idempotency_key=request_id,
        )
        run = store.update_run_trigger_result(
            request_id=request_id,
            trigger_http_status=trigger_result.http_status,
            trigger_x_request_id=trigger_result.x_request_id,
            conversation_url=trigger_result.conversation_url,
        )
        return JSONResponse(run)

    routes = [
        Route("/", endpoint=dashboard, methods=["GET"]),
        Route("/api/agents", endpoint=list_agents, methods=["GET"]),
        Route("/api/agents", endpoint=create_agent, methods=["POST"]),
        Route("/api/conversations", endpoint=list_conversations, methods=["GET"]),
        Route("/api/conversations", endpoint=create_conversation, methods=["POST"]),
        Route("/api/conversations/{conversation_id:int}/runs", endpoint=list_runs, methods=["GET"]),
        Route("/api/conversations/{conversation_id:int}/runs", endpoint=create_run, methods=["POST"]),
        Mount("/", app=mcp_app),
    ]
    app = Starlette(routes=routes)
    app.state.trigger_client = TriggerClient()
    return app
```

- [ ] **Step 5: Run API tests**

Run:

```bash
python3 -m pytest tests/test_web_api.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Run transport tests to ensure MCP still works**

Run:

```bash
python3 -m pytest tests/test_server_transport.py -q
```

Expected: `4 passed`.

- [ ] **Step 7: Run all current tests**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit local API**

Run:

```bash
git add src/workspace_agent_relay_mcp/db.py src/workspace_agent_relay_mcp/web.py tests/test_web_api.py
git commit -m "feat(api): 增加本地 relay 控制接口"
```

---

### Task 7: Add Local MCP End-To-End Test

**Files:**
- Modify: `tests/test_server_transport.py`

- [ ] **Step 1: Add streamable HTTP MCP integration test**

Append to `tests/test_server_transport.py`:

```python
import contextlib
import socket
import threading
import time

import anyio
import httpx
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def _running_server(tmp_path: Path):
    from workspace_agent_relay_mcp import server

    server.config = RelayConfig(state_dir=tmp_path / "state", auth_token="secret")
    server.store = RelayStore(server.config.database_path)
    agent = server.store.upsert_agent(name="default", trigger_url="https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger", token_ref="env:TOKEN")
    conversation = server.store.create_conversation(agent_id=agent["id"], name="Sherlog", conversation_key="research:sherlog")
    server.store.create_run(
        agent_id=agent["id"],
        conversation_id=conversation["id"],
        conversation_key="research:sherlog",
        input_markdown="task",
        callback_token="secret-callback",
        idempotency_key="run_1",
        request_id="run_1",
    )
    app = server.build_http_app()
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    uvicorn_server = uvicorn.Server(config)
    uvicorn_server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)
    else:
        raise AssertionError("Timed out waiting for relay MCP test server.")
    try:
        yield f"http://127.0.0.1:{port}/mcp", server.store
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


async def _call_tool(url: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    headers = {"Authorization": "Bearer secret"}
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        async with streamable_http_client(url, http_client=client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                assert result.isError is False
                assert result.structuredContent is not None
                return result.structuredContent


def test_mcp_record_result_end_to_end(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (url, store):

        async def scenario() -> None:
            result = await _call_tool(
                url,
                "record_result",
                {
                    "request_id": "run_1",
                    "callback_token": "secret-callback",
                    "conversation_key": "research:sherlog",
                    "status": "done",
                    "title": "Done",
                    "markdown": "Final Markdown",
                    "artifacts": [],
                },
            )
            assert result["success"] is True

        anyio.run(scenario)
        run = store.get_run_by_request_id("run_1")
        assert run["status"] == "done"
```

- [ ] **Step 2: Run integration test**

Run:

```bash
python3 -m pytest tests/test_server_transport.py::test_mcp_record_result_end_to_end -q
```

Expected: `1 passed`.

- [ ] **Step 3: Run full transport suite**

Run:

```bash
python3 -m pytest tests/test_server_transport.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 4: Commit integration test**

Run:

```bash
git add tests/test_server_transport.py
git commit -m "test(mcp): 覆盖本地回调端到端流程"
```

---

### Task 8: Add Dev Tunnel Script And Documentation

**Files:**
- Create: `scripts/dev-tunnel.sh`
- Modify: `README.md`

- [ ] **Step 1: Create dev tunnel script**

Create `scripts/dev-tunnel.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

export WORKSPACE_AGENT_RELAY_HOST="${WORKSPACE_AGENT_RELAY_HOST:-127.0.0.1}"
export WORKSPACE_AGENT_RELAY_PORT="${WORKSPACE_AGENT_RELAY_PORT:-8799}"
export WORKSPACE_AGENT_RELAY_STATE_DIR="${WORKSPACE_AGENT_RELAY_STATE_DIR:-${HOME}/.workspace-agent-relay-mcp}"

if [[ -z "${WORKSPACE_AGENT_RELAY_AUTH_TOKEN:-}" ]]; then
  echo "Missing WORKSPACE_AGENT_RELAY_AUTH_TOKEN. Set it in .env." >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/.venv/bin/activate"
pip install -e ".[dev]"

SERVER_URL="http://${WORKSPACE_AGENT_RELAY_HOST}:${WORKSPACE_AGENT_RELAY_PORT}"
python -m workspace_agent_relay_mcp.server &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

python - <<'PY'
import os
import socket
import time

host = os.environ["WORKSPACE_AGENT_RELAY_HOST"]
port = int(os.environ["WORKSPACE_AGENT_RELAY_PORT"])
deadline = time.time() + 15
while time.time() < deadline:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            raise SystemExit(0)
    time.sleep(0.2)
raise SystemExit(f"Timed out waiting for {host}:{port}")
PY

echo "Dashboard: ${SERVER_URL}/"
echo "MCP endpoint: ${SERVER_URL}/mcp"

if command -v cloudflared >/dev/null 2>&1; then
  if [[ -n "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG:-}" ]]; then
    if [[ -n "${WORKSPACE_AGENT_RELAY_TUNNEL_NAME:-}" ]]; then
      cloudflared tunnel --config "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG}" run "${WORKSPACE_AGENT_RELAY_TUNNEL_NAME}"
    else
      cloudflared tunnel --config "${WORKSPACE_AGENT_RELAY_CLOUDFLARED_CONFIG}" run
    fi
  else
    cloudflared tunnel --url "${SERVER_URL}"
  fi
else
  echo "cloudflared is not installed; local server is running until Ctrl+C."
  wait "$SERVER_PID"
fi
```

Run:

```bash
chmod +x scripts/dev-tunnel.sh
```

- [ ] **Step 2: Expand README with usage and smoke test**

Replace `README.md` with:

```markdown
# workspace-agent-relay-mcp

Local relay MCP and dashboard for ChatGPT Workspace Agent trigger runs.

The Workspace Agent trigger API accepts asynchronous work but does not currently provide a response retrieval API. This project gives the agent a narrow local MCP callback surface so it can write progress, questions, and final Markdown results back to your machine.

## What it exposes

MCP tools:

- `record_progress`
- `record_result`
- `ask_user`
- `get_run_context`
- `server_info`

It intentionally does not expose shell, arbitrary file reads, git, or arbitrary file writes.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`:

```bash
WORKSPACE_AGENT_RELAY_AUTH_TOKEN=local-mcp-token
WORKSPACE_AGENT_RELAY_TRIGGER_URL=https://api.chatgpt.com/v1/workspace_agents/agtch_your_id/trigger
WORKSPACE_AGENT_RELAY_AGENT_TOKEN=your-workspace-agent-access-token
```

Run locally:

```bash
workspace-agent-relay-mcp
```

Dashboard:

```text
http://127.0.0.1:8799/
```

MCP endpoint:

```text
http://127.0.0.1:8799/mcp
```

Run with tunnel:

```bash
./scripts/dev-tunnel.sh
```

## Workspace Agent instruction

Add an instruction like this to the Workspace Agent:

```text
When a trigger input includes request_id, conversation_key, and callback_token, use the workspace-agent-relay-mcp tools.

Before you finish, call record_result with:
- exact request_id
- exact conversation_key
- exact callback_token
- status
- title
- full Markdown result

Use record_progress for meaningful progress.
Use ask_user when blocked on a user decision.
Do not only answer in the ChatGPT conversation.
```

## Smoke test

1. Start the relay.
2. Connect the MCP endpoint to ChatGPT or the Workspace Agent runtime.
3. Open the dashboard.
4. Create or load the default agent.
5. Send a short task.
6. Confirm the dashboard shows `accepted`.
7. Confirm the agent calls `record_result`.
8. Confirm final Markdown appears in the dashboard.

## Security notes

- Keep `.env` out of git.
- Rotate any Workspace Agent access token pasted into chat or logs.
- Use a high-entropy `WORKSPACE_AGENT_RELAY_AUTH_TOKEN`.
- The callback token is per-run and is stored only as a hash.
```

- [ ] **Step 3: Run shell syntax check and tests**

Run:

```bash
bash -n scripts/dev-tunnel.sh
python3 -m pytest -q
```

Expected: shell syntax check exits 0 and all tests pass.

- [ ] **Step 4: Commit docs and script**

Run:

```bash
git add scripts/dev-tunnel.sh README.md
git commit -m "docs: 补充 relay mcp 使用说明"
```

---

### Task 9: Manual Local Smoke Verification

**Files:**
- No source changes expected unless verification finds a defect.

- [ ] **Step 1: Install package in editable mode**

Run:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: package installs without errors.

- [ ] **Step 2: Run full automated verification**

Run:

```bash
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Start local server with temporary safe env**

Run:

```bash
WORKSPACE_AGENT_RELAY_AUTH_TOKEN=local-test-token \
WORKSPACE_AGENT_RELAY_STATE_DIR="$(pwd)/.local-state" \
workspace-agent-relay-mcp
```

Expected: server starts on `127.0.0.1:8799`.

- [ ] **Step 4: Verify local dashboard and MCP discovery from another shell**

Run:

```bash
curl -fsS http://127.0.0.1:8799/ | head
curl -fsS http://127.0.0.1:8799/.well-known/mcp.json
curl -i http://127.0.0.1:8799/mcp
```

Expected:

- Dashboard returns HTML.
- MCP server card returns JSON.
- `/mcp` without auth returns `401` when auth token is set.

- [ ] **Step 5: Verify local API creates an agent and conversation**

Run:

```bash
curl -fsS -X POST http://127.0.0.1:8799/api/agents \
  -H 'Content-Type: application/json' \
  -d '{"name":"default","trigger_url":"https://api.chatgpt.com/v1/workspace_agents/agtch_test/trigger","token_ref":"env:WORKSPACE_AGENT_RELAY_AGENT_TOKEN"}'

curl -fsS -X POST http://127.0.0.1:8799/api/conversations \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":1,"name":"Test","conversation_key":"test:local"}'
```

Expected: both return JSON objects with ids.

- [ ] **Step 6: Stop server and inspect git status**

Run:

```bash
git status --short
```

Expected: no unexpected source changes. `.local-state` should be ignored or manually deleted before finalizing:

```bash
rm -rf .local-state
```

- [ ] **Step 7: Commit any verification fixes**

If verification required code or docs fixes, commit them:

```bash
git add <fixed-files>
git commit -m "fix: 修正 relay mcp smoke 验证问题"
```

If no fixes were needed, do not create an empty commit.

---

## Spec Coverage Review

- Trigger API limitation and MCP callback side channel: Tasks 3, 4, 6, 7.
- Local secrets and no browser token exposure: Tasks 1, 6, 8.
- Per-run callback token validation: Task 2 and Task 4.
- Communication-only MCP tools: Task 4.
- SQLite state model: Task 2.
- Local web app/API: Task 6.
- Streamable HTTP/OAuth/Bearer compatibility: Task 5.
- Tests for store, payload, callbacks, transport, and API: Tasks 1 through 7.
- Manual smoke test: Task 9.

## Execution Notes

- Do not add shell, filesystem, git, or arbitrary local ops tools to this project.
- Do not paste real Workspace Agent access tokens into tests, docs, commits, or final summaries.
- Use focused commits after each task.
- If ChatGPT/Workspace Agent callback behavior differs from tests, keep the local callback contract and update only the integration wording or compatibility layer needed for the real client.
