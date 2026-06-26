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
    def _connect(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        transaction_started = False
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            transaction_started = True
            yield conn
        except Exception:
            if transaction_started:
                conn.rollback()
            raise
        else:
            if transaction_started:
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
            row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {name}")
        return _row_to_dict(row) or {}

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
            conversation = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise ValueError(f"Conversation not found: {conversation_id}")
            if conversation["conversation_key"] != conversation_key:
                raise ValueError("conversation_key does not match conversation_id.")
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

    def _get_run_by_request_id_conn(self, conn: sqlite3.Connection, request_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {request_id}")
        return _row_to_dict(row) or {}

    def _redact_run(self, run: dict[str, Any]) -> dict[str, Any]:
        payload = dict(run)
        payload.pop("callback_token_hash", None)
        return payload

    def get_run_by_request_id(self, request_id: str, *, include_secret_hash: bool = False) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            payload = self._get_run_by_request_id_conn(conn, request_id)
        if not include_secret_hash:
            payload = self._redact_run(payload)
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

    def _validate_callback_conn(
        self,
        conn: sqlite3.Connection,
        request_id: str,
        conversation_key: str,
        callback_token: str,
    ) -> dict[str, Any]:
        try:
            run = self._get_run_by_request_id_conn(conn, request_id)
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
        return {"success": True, "run": self._redact_run(run)}

    def validate_callback(self, request_id: str, conversation_key: str, callback_token: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            return self._validate_callback_conn(conn, request_id, conversation_key, callback_token)

    def _append_event_conn(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: int,
        request_id: str,
        event_type: str,
        title: str | None,
        markdown: str | None,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = _now()
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
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key, callback_token)
            if not validation["success"]:
                return validation
            run = validation["run"]
            event = self._append_event_conn(
                conn,
                run_id=int(run["id"]),
                request_id=request_id,
                event_type="progress",
                title=title,
                markdown=message,
                payload=payload,
            )
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
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key, callback_token)
            if not validation["success"]:
                return validation
            run = validation["run"]
            event = self._append_event_conn(
                conn,
                run_id=int(run["id"]),
                request_id=request_id,
                event_type="question",
                title="User input needed",
                markdown=question,
                payload={"choices": choices or [], "context": context or ""},
            )
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
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key, callback_token)
            if not validation["success"]:
                return validation
            run = validation["run"]
            self._append_event_conn(
                conn,
                run_id=int(run["id"]),
                request_id=request_id,
                event_type="result",
                title=title,
                markdown=markdown,
                payload={"status": status},
            )
            now = _now()
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
