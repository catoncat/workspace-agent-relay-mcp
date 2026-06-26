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
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from .bus import RunEventBus


TERMINAL_STATUSES = {"done", "blocked", "failed"}
VALID_RESULT_STATUSES = TERMINAL_STATUSES
TRIGGER_MUTABLE_RUN_STATUSES = {"draft", "sent"}
VALID_STEP_STATUSES = {"pending", "in_progress", "done", "skipped"}
MAX_PLAN_STEPS = 20
MAX_STEP_TITLE_LEN = 200
REDACTED_CALLBACK_TOKEN = "[redacted-callback-token]"


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


def _redact_callback_token(value: Any, callback_token: str) -> Any:
    if not callback_token:
        return value
    if isinstance(value, str):
        return value.replace(callback_token, REDACTED_CALLBACK_TOKEN)
    if isinstance(value, dict):
        return {
            (
                _redact_callback_token(key, callback_token)
                if isinstance(key, str)
                else key
            ): _redact_callback_token(item, callback_token)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_callback_token(item, callback_token) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_callback_token(item, callback_token) for item in value)
    return value


def _redact_artifact_scalar(value: Any, callback_token: str, default: str) -> str:
    scalar = value or default
    return _redact_callback_token(str(scalar), callback_token)


def _extract_trigger_id(trigger_url: str) -> str:
    match = re.search(r"/workspace_agents/([^/]+)/trigger$", trigger_url)
    return match.group(1) if match else ""


def _normalize_plan_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    if not steps:
        raise ValueError("steps must not be empty")
    if len(steps) > MAX_PLAN_STEPS:
        raise ValueError(f"steps must not exceed {MAX_PLAN_STEPS} items")
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"step {index} must be an object")
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError(f"step {index} is missing a non-empty id")
        step_id = step_id.strip()
        if step_id in seen_ids:
            raise ValueError(f"step id {step_id!r} is duplicated")
        seen_ids.add(step_id)
        title = step.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"step {step_id!r} is missing a non-empty title")
        title = title.strip()
        if len(title) > MAX_STEP_TITLE_LEN:
            raise ValueError(f"step {step_id!r} title exceeds {MAX_STEP_TITLE_LEN} chars")
        status = step.get("status") or "pending"
        if status not in VALID_STEP_STATUSES:
            raise ValueError(f"step {step_id!r} has invalid status {status!r}")
        note = step.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError(f"step {step_id!r} note must be a string")
        normalized.append(
            {
                "id": step_id,
                "title": title,
                "status": status,
                "note": (note or ""),
            }
        )
    return normalized


def _normalize_step_updates(updates: Any) -> list[dict[str, Any]]:
    if not isinstance(updates, list):
        raise ValueError("step_updates must be a list")
    normalized: list[dict[str, Any]] = []
    for index, update in enumerate(updates):
        if not isinstance(update, dict):
            raise ValueError(f"step_updates[{index}] must be an object")
        step_id = update.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError(f"step_updates[{index}] is missing a non-empty id")
        status = update.get("status")
        if status is not None and status not in VALID_STEP_STATUSES:
            raise ValueError(f"step_updates[{index}] has invalid status {status!r}")
        note = update.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError(f"step_updates[{index}] note must be a string")
        normalized.append(
            {
                "id": step_id.strip(),
                "status": status,
                "note": note,
            }
        )
    return normalized


class RelayStore:
    def __init__(self, database_path: Path, *, event_bus: RunEventBus | None = None) -> None:
        self.database_path = database_path
        self._event_bus = event_bus
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.database_path.parent.chmod(0o700)
        except OSError:
            pass
        self._lock = threading.RLock()
        self._init_schema()

    def _notify_run(self, run_id: int) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(
                run_id,
                {
                    "run": self.get_run(run_id),
                    "events": self.list_events(run_id),
                    "artifacts": self.list_artifacts(run_id),
                    "plan": self.get_plan(run_id),
                },
            )
        except KeyError:
            return

    def _notify_run_by_request_id(self, request_id: str) -> None:
        try:
            run = self.get_run_by_request_id(request_id)
        except KeyError:
            return
        self._notify_run(int(run["id"]))

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
                CREATE TABLE IF NOT EXISTS plans (
                    run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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

    def rename_conversation(self, conversation_id: int, *, name: str) -> dict[str, Any]:
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            conn.execute(
                "UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?",
                (name.strip(), now, conversation_id),
            )
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        return _row_to_dict(row) or {}

    def delete_conversation(self, conversation_id: int) -> None:
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id = ? AND archived_at IS NULL",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            conn.execute(
                "UPDATE conversations SET archived_at = ?, updated_at = ? WHERE id = ?",
                (now, now, conversation_id),
            )

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
        redacted_input_markdown = _redact_callback_token(input_markdown, callback_token)
        with self._lock, self._connect() as conn:
            conversation = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise ValueError(f"Conversation not found: {conversation_id}")
            if conversation["conversation_key"] != conversation_key:
                raise ValueError("conversation_key does not match conversation_id.")
            if conversation["agent_id"] != agent_id:
                raise ValueError("agent_id does not own conversation_id.")
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
                    redacted_input_markdown,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        payload = _row_to_dict(row) or {}
        payload.pop("callback_token_hash", None)
        self._notify_run(int(payload["id"]))
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

    def get_run(self, run_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        return self._redact_run(_row_to_dict(row) or {})

    def _get_plan_conn(self, conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM plans WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        payload = _row_to_dict(row) or {}
        try:
            steps = json.loads(payload.get("steps_json") or "[]")
        except json.JSONDecodeError:
            steps = []
        if not isinstance(steps, list):
            steps = []
        return {
            "run_id": int(payload["run_id"]),
            "steps": steps,
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }

    def get_plan(self, run_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            return self._get_plan_conn(conn, run_id)

    def record_plan(
        self,
        *,
        request_id: str,
        conversation_key: str,
        callback_token: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            normalized = _normalize_plan_steps(steps)
        except ValueError as exc:
            return {"success": False, "error": {"code": "invalid_plan", "message": str(exc)}}
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key, callback_token)
            if not validation["success"]:
                return validation
            run = validation["run"]
            run_id = int(run["id"])
            now = _now()
            redacted_steps = _redact_callback_token(normalized, callback_token)
            conn.execute(
                """
                INSERT INTO plans (run_id, steps_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    updated_at = excluded.updated_at
                """,
                (run_id, _json_dumps(redacted_steps), now, now),
            )
            self._append_event_conn(
                conn,
                run_id=run_id,
                request_id=request_id,
                event_type="plan",
                title="Plan updated",
                markdown=None,
                payload={"steps": redacted_steps},
            )
        plan = self.get_plan(run_id)
        self._notify_run(run_id)
        return {"success": True, "plan": plan, "run_status": self.get_run(run_id)["status"]}

    def update_run_trigger_result(
        self,
        *,
        request_id: str,
        trigger_http_status: int,
        trigger_x_request_id: str | None,
        conversation_url: str | None,
    ) -> dict[str, Any]:
        trigger_status = "accepted" if 200 <= trigger_http_status < 300 else "failed"
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            run = self._get_run_by_request_id_conn(conn, request_id)
            status = trigger_status if run["status"] in TRIGGER_MUTABLE_RUN_STATUSES else run["status"]
            conn.execute(
                """
                UPDATE runs
                SET status = ?, trigger_status = ?, trigger_http_status = ?,
                    trigger_x_request_id = ?, conversation_url = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status, trigger_status, trigger_http_status, trigger_x_request_id, conversation_url, now, request_id),
            )
        result = self.get_run_by_request_id(request_id)
        self._notify_run(int(result["id"]))
        return result

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
        expected = str(run["callback_token_hash"])
        actual = _hash_token(callback_token)
        if not hmac.compare_digest(expected, actual):
            return {"success": False, "error": {"code": "invalid_callback_token", "message": "callback_token is invalid."}}
        if run["status"] in TERMINAL_STATUSES:
            return {"success": False, "error": {"code": "run_closed", "message": "Run is already terminal."}}
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
        step_updates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            normalized_updates = _normalize_step_updates(step_updates) if step_updates else []
        except ValueError as exc:
            return {"success": False, "error": {"code": "invalid_step_updates", "message": str(exc)}}
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key, callback_token)
            if not validation["success"]:
                return validation
            run = validation["run"]
            run_id = int(run["id"])
            existing_plan = self._get_plan_conn(conn, run_id)
            applied_updates: list[dict[str, Any]] = []
            ignored_ids: list[str] = []
            if normalized_updates and existing_plan is not None:
                steps_by_id = {step["id"]: step for step in existing_plan["steps"]}
                for update in normalized_updates:
                    step = steps_by_id.get(update["id"])
                    if step is None:
                        ignored_ids.append(update["id"])
                        continue
                    if update["status"] is not None:
                        step["status"] = update["status"]
                    if update["note"] is not None:
                        step["note"] = update["note"]
                    applied_updates.append({"id": update["id"], "status": step["status"], "note": step["note"]})
                redacted_steps = _redact_callback_token(existing_plan["steps"], callback_token)
                conn.execute(
                    "UPDATE plans SET steps_json = ?, updated_at = ? WHERE run_id = ?",
                    (_json_dumps(redacted_steps), _now(), run_id),
                )
            elif normalized_updates and existing_plan is None:
                ignored_ids = [update["id"] for update in normalized_updates]
            progress_payload: dict[str, Any] = dict(payload or {})
            if applied_updates:
                progress_payload["step_updates"] = applied_updates
            if ignored_ids:
                progress_payload["ignored_step_ids"] = ignored_ids
            event = self._append_event_conn(
                conn,
                run_id=run_id,
                request_id=request_id,
                event_type="progress",
                title=_redact_callback_token(title, callback_token),
                markdown=_redact_callback_token(message, callback_token),
                payload=_redact_callback_token(progress_payload, callback_token),
            )
            conn.execute("UPDATE runs SET status = 'waiting', updated_at = ? WHERE id = ?", (_now(), run_id))
        plan = self.get_plan(run_id)
        self._notify_run(run_id)
        return {"success": True, "event_id": event["id"], "plan": plan, "run_status": "waiting"}

    def record_tool_trace(
        self,
        *,
        request_id: str,
        conversation_key: str,
        callback_token: str,
        tool: str,
        title: str,
        args_summary: dict[str, Any] | None = None,
        result_summary: dict[str, Any] | None = None,
        started_at: str | None = None,
        duration_ms: int | float | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key, callback_token)
            if not validation["success"]:
                return validation
            run = validation["run"]
            run_id = int(run["id"])
            markdown = self._format_trace_markdown(tool, title, ok, error, duration_ms)
            payload = {
                "trace": True,
                "tool": tool,
                "title": title,
                "args_summary": args_summary,
                "result_summary": result_summary,
                "started_at": started_at,
                "duration_ms": duration_ms,
                "ok": ok,
                "error": error,
            }
            event = self._append_event_conn(
                conn,
                run_id=run_id,
                request_id=request_id,
                event_type="progress",
                title=_redact_callback_token(title, callback_token),
                markdown=_redact_callback_token(markdown, callback_token),
                payload=_redact_callback_token(payload, callback_token),
            )
        self._notify_run(run_id)
        return {"success": True, "event_id": event["id"]}

    @staticmethod
    def _format_trace_markdown(
        tool: str,
        title: str,
        ok: bool,
        error: str | None,
        duration_ms: int | float | None,
    ) -> str:
        marker = "✓" if ok else "✗"
        target = title or tool
        parts: list[str] = [f"{marker} {tool}"]
        if target and target != tool:
            parts.append(target)
        if duration_ms is not None:
            parts.append(f"({int(duration_ms)}ms)")
        summary = " ".join(parts)
        if not ok and error:
            truncated = error.strip().replace("\n", " ")
            if len(truncated) > 160:
                truncated = truncated[:159] + "…"
            summary += f" (failed: {truncated})"
        return summary

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
                markdown=_redact_callback_token(question, callback_token),
                payload=_redact_callback_token(
                    {"choices": choices or [], "context": context or ""},
                    callback_token,
                ),
            )
            conn.execute("UPDATE runs SET status = 'needs_user', updated_at = ? WHERE id = ?", (_now(), run["id"]))
        self._notify_run(int(run["id"]))
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
                title=_redact_callback_token(title, callback_token),
                markdown=_redact_callback_token(markdown, callback_token),
                payload={"status": status},
            )
            now = _now()
            for artifact in artifacts or []:
                redacted_metadata = _redact_callback_token(artifact.get("metadata") or {}, callback_token)
                conn.execute(
                    """
                    INSERT INTO artifacts (run_id, name, mime_type, content, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run["id"],
                        _redact_artifact_scalar(artifact.get("name"), callback_token, "artifact.txt"),
                        _redact_artifact_scalar(artifact.get("mime_type"), callback_token, "text/plain"),
                        _redact_artifact_scalar(artifact.get("content"), callback_token, ""),
                        _json_dumps(redacted_metadata),
                        now,
                    ),
                )
            conn.execute(
                "UPDATE runs SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (status, now, now, run["id"]),
            )
        self._notify_run(int(run["id"]))
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
