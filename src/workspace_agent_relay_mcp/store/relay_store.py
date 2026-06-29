from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from ..run_lifecycle import (
    TERMINAL_STATUSES,
    TRIGGER_MUTABLE_RUN_STATUSES,
    USER_REPLY_STATUSES,
    VALID_RESULT_STATUSES,
    after_operator_steer,
    after_plan,
    after_progress,
    after_tool_trace,
    after_trigger_result,
    after_trigger_sent,
    after_user_question,
)

if TYPE_CHECKING:
    from .bus import RunEventBus


VALID_STEP_STATUSES = {"pending", "in_progress", "done", "skipped"}
MAX_PLAN_STEPS = 20
MAX_STEP_TITLE_LEN = 200
AGENT_PUBLIC_COLUMNS = "id, name, trigger_url, trigger_id, token_ref, created_at, updated_at"
WORKSPACE_PUBLIC_COLUMNS = "id, name, working_directory, created_at, updated_at, last_used_at"
CONVERSATION_PUBLIC_COLUMNS = (
    "id, agent_id, workspace_id, name, conversation_key, created_at, updated_at, archived_at, pinned_at"
)
RUN_PUBLIC_COLUMNS = (
    "id, request_id, agent_id, conversation_id, conversation_key, "
    "workspace_id, working_directory_snapshot, "
    "parent_run_id, superseded_by_run_id, supersede_reason, trigger_error, "
    "idempotency_key, input_markdown, trigger_status, trigger_http_status, "
    "trigger_x_request_id, conversation_url, status, created_at, updated_at, completed_at"
)
APP_SETTING_CURRENT_AGENT_ID = "current_agent_id"
APP_SETTING_CURRENT_WORKSPACE_ID = "current_workspace_id"
_UNSET = object()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _extract_trigger_id(trigger_url: str) -> str:
    match = re.search(r"/workspace_agents/([^/]+)/trigger$", trigger_url)
    return match.group(1) if match else ""


def _normalize_working_directory(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("working_directory must be an absolute path")
    return str(path)


def _normalize_workspace_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("name must not be empty")
    return name


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
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    working_directory TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT
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
                    parent_run_id INTEGER,
                    superseded_by_run_id INTEGER,
                    supersede_reason TEXT,
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
            # Forward-only migrations: add columns to existing databases.
            # SQLite's ALTER TABLE ADD COLUMN is idempotent-safe when guarded by
            # a table_info check. New databases get the column via the path below
            # too (cheaper than branching on fresh-vs-existing).
            cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
            run_migrations = {
                "trigger_error": "TEXT",
                "parent_run_id": "INTEGER",
                "superseded_by_run_id": "INTEGER",
                "supersede_reason": "TEXT",
                "workspace_id": "INTEGER",
                "working_directory_snapshot": "TEXT",
            }
            for column, column_type in run_migrations.items():
                if column not in cols:
                    conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {column_type}")
            # Drop the legacy callback_token_hash column by rebuilding the runs
            # table (SQLite cannot DROP COLUMN portably). The callback_token was
            # removed from the protocol; existing rows are copied minus that
            # column. One-shot: only runs when an old DB still has the column.
            # foreign_keys must be OFF during the rebuild, otherwise DROP TABLE
            # runs triggers ON DELETE CASCADE and wipes events/artifacts/plans.
            # executescript first commits the outer BEGIN, so the PRAGMA takes
            # effect (foreign_keys cannot be changed inside a transaction).
            if "callback_token_hash" in cols:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = OFF;
                    CREATE TABLE runs_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT NOT NULL UNIQUE,
                        agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        conversation_key TEXT NOT NULL,
                        workspace_id INTEGER,
                        working_directory_snapshot TEXT,
                        parent_run_id INTEGER,
                        superseded_by_run_id INTEGER,
                        supersede_reason TEXT,
                        trigger_error TEXT,
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
                    INSERT INTO runs_new (
                        id, request_id, agent_id, conversation_id, conversation_key,
                        workspace_id, working_directory_snapshot,
                        parent_run_id, superseded_by_run_id, supersede_reason, trigger_error,
                        idempotency_key, input_markdown, trigger_status, trigger_http_status,
                        trigger_x_request_id, conversation_url, status, created_at, updated_at,
                        completed_at
                    )
                    SELECT
                        id, request_id, agent_id, conversation_id, conversation_key,
                        workspace_id, working_directory_snapshot,
                        parent_run_id, superseded_by_run_id, supersede_reason, trigger_error,
                        idempotency_key, input_markdown, trigger_status, trigger_http_status,
                        trigger_x_request_id, conversation_url, status, created_at, updated_at,
                        completed_at
                    FROM runs;
                    DROP TABLE runs;
                    ALTER TABLE runs_new RENAME TO runs;
                    PRAGMA foreign_key_check;
                    PRAGMA foreign_keys = ON;
                    """
                )
            conv_cols = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
            conv_migrations = {
                "pinned_at": "TEXT",
                "workspace_id": "INTEGER",
            }
            for column, column_type in conv_migrations.items():
                if column not in conv_cols:
                    conn.execute(f"ALTER TABLE conversations ADD COLUMN {column} {column_type}")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_secrets (
                    agent_id INTEGER PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
                    access_token TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _setting_value_conn(self, conn: sqlite3.Connection, key: str) -> Any:
        row = conn.execute("SELECT value_json FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(str(row["value_json"]))
        except json.JSONDecodeError:
            return None

    def _set_setting_conn(self, conn: sqlite3.Connection, key: str, value: Any) -> None:
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
            """,
            (key, _json_dumps(value)),
        )

    def _agent_exists_conn(self, conn: sqlite3.Connection, agent_id: int) -> bool:
        return conn.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone() is not None

    def _workspace_exists_conn(self, conn: sqlite3.Connection, workspace_id: int) -> bool:
        return conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone() is not None

    def _first_agent_id_conn(self, conn: sqlite3.Connection) -> int | None:
        row = conn.execute("SELECT id FROM agents ORDER BY name, id LIMIT 1").fetchone()
        return int(row["id"]) if row is not None else None

    def _get_settings_conn(self, conn: sqlite3.Connection) -> dict[str, Any]:
        raw_agent_id = self._setting_value_conn(conn, APP_SETTING_CURRENT_AGENT_ID)
        current_agent_id: int | None = None
        if raw_agent_id is not None:
            try:
                candidate = int(raw_agent_id)
            except (TypeError, ValueError):
                candidate = 0
            if candidate and self._agent_exists_conn(conn, candidate):
                current_agent_id = candidate
        if current_agent_id is None:
            current_agent_id = self._first_agent_id_conn(conn)

        raw_workspace_id = self._setting_value_conn(conn, APP_SETTING_CURRENT_WORKSPACE_ID)
        current_workspace_id: int | None = None
        if raw_workspace_id is not None:
            try:
                candidate = int(raw_workspace_id)
            except (TypeError, ValueError):
                candidate = 0
            if candidate and self._workspace_exists_conn(conn, candidate):
                current_workspace_id = candidate

        return {
            "current_agent_id": current_agent_id,
            "current_workspace_id": current_workspace_id,
        }

    def get_settings(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            return self._get_settings_conn(conn)

    def update_settings(
        self,
        *,
        current_agent_id: Any = _UNSET,
        current_workspace_id: Any = _UNSET,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            if current_agent_id is not _UNSET:
                if current_agent_id is None:
                    self._set_setting_conn(conn, APP_SETTING_CURRENT_AGENT_ID, None)
                else:
                    agent_id = int(current_agent_id)
                    if not self._agent_exists_conn(conn, agent_id):
                        raise KeyError(f"Agent not found: {agent_id}")
                    self._set_setting_conn(conn, APP_SETTING_CURRENT_AGENT_ID, agent_id)
            if current_workspace_id is not _UNSET:
                if current_workspace_id is None:
                    self._set_setting_conn(conn, APP_SETTING_CURRENT_WORKSPACE_ID, None)
                else:
                    workspace_id = int(current_workspace_id)
                    if not self._workspace_exists_conn(conn, workspace_id):
                        raise KeyError(f"Workspace not found: {workspace_id}")
                    self._set_setting_conn(conn, APP_SETTING_CURRENT_WORKSPACE_ID, workspace_id)
                    conn.execute(
                        "UPDATE workspaces SET last_used_at = ? WHERE id = ?",
                        (now, workspace_id),
                    )
            return self._get_settings_conn(conn)

    def resolve_default_agent_id(self) -> int:
        settings = self.get_settings()
        agent_id = settings.get("current_agent_id")
        if agent_id is None:
            raise ValueError("No Workspace Agent backend is configured.")
        return int(agent_id)

    def resolve_default_workspace_id(self) -> int | None:
        settings = self.get_settings()
        workspace_id = settings.get("current_workspace_id")
        return int(workspace_id) if workspace_id is not None else None

    def get_agent(self, agent_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {agent_id}")
        return _row_to_dict(row) or {}

    def get_agent_access_token(self, agent_id: int) -> str:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT access_token FROM agent_secrets WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
        if row is None:
            return ""
        return str(row["access_token"] or "").strip()

    def set_agent_access_token(self, agent_id: int, *, access_token: str) -> None:
        token = access_token.strip()
        if not token:
            raise ValueError("access_token must not be empty")
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if row is None:
                raise KeyError(f"Agent not found: {agent_id}")
            conn.execute(
                """
                INSERT INTO agent_secrets (agent_id, access_token, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    updated_at = excluded.updated_at
                """,
                (agent_id, token, now),
            )
            conn.execute(
                "UPDATE agents SET token_ref = ?, updated_at = ? WHERE id = ?",
                (f"local:{agent_id}", now, agent_id),
            )

    def create_agent(self, *, name: str, trigger_url: str, access_token: str) -> dict[str, Any]:
        token = access_token.strip()
        if not token:
            raise ValueError("access_token must not be empty")
        now = _now()
        trigger_id = _extract_trigger_id(trigger_url)
        with self._lock, self._connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                INSERT INTO agents (name, trigger_url, trigger_id, token_ref, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, trigger_url, trigger_id, "local:pending", now, now),
            )
            agent_id = int(cursor.lastrowid)
            token_ref = f"local:{agent_id}"
            conn.execute(
                "UPDATE agents SET token_ref = ? WHERE id = ?",
                (token_ref, agent_id),
            )
            conn.execute(
                """
                INSERT INTO agent_secrets (agent_id, access_token, updated_at)
                VALUES (?, ?, ?)
                """,
                (agent_id, token, now),
            )
            row = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {agent_id}")
        return _row_to_dict(row) or {}

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
            row = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {name}")
        return _row_to_dict(row) or {}

    def get_agent_by_name(self, name: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {name}")
        return _row_to_dict(row) or {}

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents ORDER BY name").fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def get_workspace(self, workspace_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT {WORKSPACE_PUBLIC_COLUMNS} FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Workspace not found: {workspace_id}")
        return _row_to_dict(row) or {}

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {WORKSPACE_PUBLIC_COLUMNS}
                FROM workspaces
                ORDER BY COALESCE(last_used_at, updated_at) DESC, name COLLATE NOCASE ASC, id ASC
                """
            ).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def create_workspace(self, *, name: str, working_directory: Any = None) -> dict[str, Any]:
        normalized_name = _normalize_workspace_name(name)
        normalized_directory = _normalize_working_directory(working_directory)
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            cursor = conn.execute(
                """
                INSERT INTO workspaces (name, working_directory, created_at, updated_at, last_used_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_name, normalized_directory, now, now, now),
            )
            row = conn.execute(
                f"SELECT {WORKSPACE_PUBLIC_COLUMNS} FROM workspaces WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        if row is None:
            raise KeyError("Workspace not found after create")
        return _row_to_dict(row) or {}

    def update_workspace(
        self,
        workspace_id: int,
        *,
        name: Any = _UNSET,
        working_directory: Any = _UNSET,
    ) -> dict[str, Any]:
        if name is _UNSET and working_directory is _UNSET:
            raise ValueError("no fields to update")
        now = _now()
        sets = ["updated_at = ?"]
        params: list[Any] = [now]
        if name is not _UNSET:
            sets.append("name = ?")
            params.append(_normalize_workspace_name(name))
        if working_directory is not _UNSET:
            sets.append("working_directory = ?")
            params.append(_normalize_working_directory(working_directory))
        params.append(workspace_id)
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if row is None:
                raise KeyError(f"Workspace not found: {workspace_id}")
            conn.execute(f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ?", params)
            row = conn.execute(
                f"SELECT {WORKSPACE_PUBLIC_COLUMNS} FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
        return _row_to_dict(row) or {}

    def delete_workspace(self, workspace_id: int) -> None:
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if row is None:
                raise KeyError(f"Workspace not found: {workspace_id}")
            settings = self._get_settings_conn(conn)
            conn.execute(
                "UPDATE conversations SET workspace_id = NULL, updated_at = ? WHERE workspace_id = ?",
                (_now(), workspace_id),
            )
            conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            if settings.get("current_workspace_id") == workspace_id:
                self._set_setting_conn(conn, APP_SETTING_CURRENT_WORKSPACE_ID, None)

    def create_conversation(
        self,
        *,
        agent_id: int,
        name: str,
        conversation_key: str,
        workspace_id: int | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect() as conn:
            if workspace_id is not None and not self._workspace_exists_conn(conn, int(workspace_id)):
                raise KeyError(f"Workspace not found: {workspace_id}")
            conn.execute(
                """
                INSERT INTO conversations (agent_id, workspace_id, name, conversation_key, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (agent_id, workspace_id, name, conversation_key, now, now),
            )
            row = conn.execute(
                f"SELECT {CONVERSATION_PUBLIC_COLUMNS} FROM conversations WHERE conversation_key = ?",
                (conversation_key,),
            ).fetchone()
        return _row_to_dict(row) or {}

    def list_conversations(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {CONVERSATION_PUBLIC_COLUMNS}
                FROM conversations
                WHERE archived_at IS NULL
                ORDER BY (pinned_at IS NULL) ASC, pinned_at DESC, updated_at DESC
                """
            ).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def get_conversation(self, conversation_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT {CONVERSATION_PUBLIC_COLUMNS} FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        return _row_to_dict(row) or {}

    def get_agent_by_trigger_id(self, trigger_id: str) -> dict[str, Any] | None:
        tid = trigger_id.strip()
        if not tid:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents WHERE trigger_id = ?", (tid,)).fetchone()
        return _row_to_dict(row)

    def rename_agent(self, agent_id: int, *, name: str) -> dict[str, Any]:
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            conn.execute(
                "UPDATE agents SET name = ?, updated_at = ? WHERE id = ?",
                (name.strip(), now, agent_id),
            )
            row = conn.execute(f"SELECT {AGENT_PUBLIC_COLUMNS} FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(f"Agent not found: {agent_id}")
        return _row_to_dict(row) or {}

    def update_conversation(self, conversation_id: int, **fields: Any) -> dict[str, Any]:
        allowed = {"name", "pinned"}
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise ValueError(f"unsupported field(s): {', '.join(unknown)}")
        if not fields:
            raise ValueError("no fields to update")
        now = _now()
        sets = ["updated_at = ?"]
        params: list[Any] = [now]
        if "name" in fields:
            name = str(fields["name"]).strip()
            if not name:
                raise ValueError("name must not be empty")
            sets.append("name = ?")
            params.append(name)
        if "pinned" in fields:
            sets.append("pinned_at = ?")
            params.append(now if bool(fields["pinned"]) else None)
        params.append(conversation_id)
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id = ? AND archived_at IS NULL",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Conversation not found: {conversation_id}")
            conn.execute(
                f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            row = conn.execute(
                f"SELECT {CONVERSATION_PUBLIC_COLUMNS} FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return _row_to_dict(row) or {}

    def rename_conversation(self, conversation_id: int, *, name: str) -> dict[str, Any]:
        return self.update_conversation(conversation_id, name=name)

    def set_conversation_pinned(self, conversation_id: int, *, pinned: bool) -> dict[str, Any]:
        return self.update_conversation(conversation_id, pinned=pinned)

    def delete_agent(self, agent_id: int) -> None:
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if row is None:
                raise KeyError(f"Agent not found: {agent_id}")
            settings = self._get_settings_conn(conn)
            conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            if settings.get("current_agent_id") == agent_id:
                next_agent_id = self._first_agent_id_conn(conn)
                self._set_setting_conn(conn, APP_SETTING_CURRENT_AGENT_ID, next_agent_id)

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
        idempotency_key: str,
        request_id: str,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            conversation = conn.execute(
                f"SELECT {CONVERSATION_PUBLIC_COLUMNS} FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                raise ValueError(f"Conversation not found: {conversation_id}")
            if conversation["conversation_key"] != conversation_key:
                raise ValueError("conversation_key does not match conversation_id.")
            if conversation["agent_id"] != agent_id:
                raise ValueError("agent_id does not own conversation_id.")
            existing_rows = conn.execute(
                "SELECT id, status FROM runs WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
            active_run_ids = [int(row["id"]) for row in existing_rows if row["status"] not in TERMINAL_STATUSES]
            parent_run_id = active_run_ids[-1] if active_run_ids else None
            workspace_id = conversation["workspace_id"]
            working_directory_snapshot = None
            if workspace_id is not None:
                workspace = conn.execute(
                    "SELECT working_directory FROM workspaces WHERE id = ?",
                    (workspace_id,),
                ).fetchone()
                if workspace is not None:
                    working_directory_snapshot = workspace["working_directory"]
            conn.execute(
                """
                INSERT INTO runs (
                    request_id, agent_id, conversation_id, conversation_key,
                    workspace_id, working_directory_snapshot,
                    idempotency_key, input_markdown, parent_run_id,
                    status, trigger_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'draft', ?, ?)
                """,
                (
                    request_id,
                    agent_id,
                    conversation_id,
                    conversation_key,
                    workspace_id,
                    working_directory_snapshot,
                    idempotency_key,
                    input_markdown,
                    parent_run_id,
                    now,
                    now,
                ),
            )
            row = conn.execute(f"SELECT {RUN_PUBLIC_COLUMNS} FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        payload = _row_to_dict(row) or {}
        self._notify_run(int(payload["id"]))
        return payload

    def mark_run_trigger_sent(self, request_id: str) -> dict[str, Any]:
        """Mark a newly-created run as dispatched to the trigger API.

        The actual trigger HTTP result is recorded later by
        update_run_trigger_result(). Keeping this as a separate transition lets
        the dashboard stop showing the local "triggering" submit state without
        pretending ChatGPT has already accepted the trigger.
        """
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            run = self._get_run_by_request_id_conn(conn, request_id)
            status = after_trigger_sent(str(run["status"]))
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE request_id = ?",
                (status, now, request_id),
            )
        result = self.get_run_by_request_id(request_id)
        self._notify_run(int(result["id"]))
        return result

    def steer_run(
        self,
        *,
        run_id: int,
        user_input: str,
    ) -> dict[str, Any]:
        """Operator adds a mid-turn instruction to an active run (steer).

        The request_id is preserved so the turn identity stays the same; the
        agent's subsequent record_plan / record_progress / record_result land on
        this same run. The run's status is advanced out of a paused question
        state if needed; no credential rotation is involved (callbacks are
        authenticated by the MCP/OAuth layer plus request_id routing).

        Raises KeyError if the run does not exist, ValueError if it is already
        terminal (the operator should send a new turn instead).
        """
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute(f"SELECT {RUN_PUBLIC_COLUMNS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"Run not found: {run_id}")
            run = _row_to_dict(row) or {}
            if run["status"] in TERMINAL_STATUSES:
                raise ValueError("Run is already terminal; send a new turn instead.")
            # Answering a paused question (needs_user) resumes the turn: a fresh
            # trigger is about to be dispatched, so the run leaves the question
            # state. Reset to "sent" so the upcoming trigger-result update advances
            # it to "accepted" (agent resuming) on a 202. Other active states
            # (running, progress, waiting, accepted) are left untouched — the agent
            # is mid-work there and the steer is added guidance, not a resume.
            next_status = after_operator_steer(str(run["status"]))
            conn.execute(
                """
                UPDATE runs
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, now, run_id),
            )
            self._append_event_conn(
                conn,
                run_id=run_id,
                request_id="dashboard",
                event_type="user_message",
                title=None,
                markdown=user_input,
                payload={
                    "source": "operator_steer",
                    "turn_ord": self._dashboard_steer_count_conn(conn, run_id) + 1,
                },
            )
        self._notify_run(run_id)
        return self.get_run(run_id)

    def _get_run_by_request_id_conn(self, conn: sqlite3.Connection, request_id: str) -> dict[str, Any]:
        row = conn.execute(f"SELECT {RUN_PUBLIC_COLUMNS} FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {request_id}")
        return _row_to_dict(row) or {}

    def get_run_by_request_id(self, request_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            return self._get_run_by_request_id_conn(conn, request_id)

    def get_run(self, run_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(f"SELECT {RUN_PUBLIC_COLUMNS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        return _row_to_dict(row) or {}

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
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            normalized = _normalize_plan_steps(steps)
        except ValueError as exc:
            return {"success": False, "error": {"code": "invalid_plan", "message": str(exc)}}
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key)
            if not validation["success"]:
                return validation
            run = validation["run"]
            run_id = int(run["id"])
            now = _now()
            conn.execute(
                """
                INSERT INTO plans (run_id, steps_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    updated_at = excluded.updated_at
                """,
                (run_id, _json_dumps(normalized), now, now),
            )
            self._append_event_conn(
                conn,
                run_id=run_id,
                request_id=request_id,
                event_type="plan",
                title="Plan updated",
                markdown=None,
                payload={"steps": normalized},
            )
            next_status = after_plan(str(run["status"]))
            if next_status != run["status"]:
                conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE id = ?", (next_status, now, run_id))
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
        trigger_error: str | None = None,
    ) -> dict[str, Any]:
        trigger_status = "accepted" if 200 <= trigger_http_status < 300 else "failed"
        # On trigger failure, mark the run trigger_failed (non-terminal) instead of
        # failed (terminal). The ChatGPT trigger API is async and may still have
        # dispatched the agent even when we got no 202 (timeout/connection error).
        # A non-terminal status lets a live agent's record_plan/record_progress/
        # record_result write back and advance the run, instead of being rejected
        # with run_closed. If no callback ever arrives, the run stays trigger_failed
        # (harvest-to-failed can be added later).
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            run = self._get_run_by_request_id_conn(conn, request_id)
            status = after_trigger_result(str(run["status"]), trigger_status=trigger_status)
            conn.execute(
                """
                UPDATE runs
                SET status = ?, trigger_status = ?, trigger_http_status = ?,
                    trigger_x_request_id = ?, conversation_url = ?, trigger_error = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status, trigger_status, trigger_http_status, trigger_x_request_id, conversation_url, trigger_error, now, request_id),
            )
        result = self.get_run_by_request_id(request_id)
        self._notify_run(int(result["id"]))
        return result

    def _validate_callback_conn(
        self,
        conn: sqlite3.Connection,
        request_id: str,
        conversation_key: str,
    ) -> dict[str, Any]:
        try:
            run = self._get_run_by_request_id_conn(conn, request_id)
        except KeyError:
            return {"success": False, "error": {"code": "run_not_found", "message": "Run was not found."}}
        if run["conversation_key"] != conversation_key:
            return {"success": False, "error": {"code": "conversation_mismatch", "message": "conversation_key does not match run."}}
        if run["status"] in TERMINAL_STATUSES:
            return {"success": False, "error": {"code": "run_closed", "message": "Run is already terminal."}}
        return {"success": True, "run": run}

    def _dashboard_steer_count_conn(self, conn: sqlite3.Connection, run_id: int) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE run_id = ? AND event_type = 'user_message'",
            (run_id,),
        ).fetchone()
        return int(row["n"] or 0)

    def _active_turn_ord_conn(self, conn: sqlite3.Connection, run_id: int) -> int:
        """Turn index for tool traces: latest steer, or 0 before any dashboard steer."""
        row = conn.execute(
            """
            SELECT payload_json FROM events
            WHERE run_id = ? AND event_type = 'user_message'
            ORDER BY id DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return 0
        payload = json.loads(str(row["payload_json"] or "{}"))
        turn_ord = payload.get("turn_ord")
        if isinstance(turn_ord, int):
            return turn_ord
        return self._dashboard_steer_count_conn(conn, run_id)

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
            validation = self._validate_callback_conn(conn, request_id, conversation_key)
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
                conn.execute(
                    "UPDATE plans SET steps_json = ?, updated_at = ? WHERE run_id = ?",
                    (_json_dumps(existing_plan["steps"]), _now(), run_id),
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
                title=title,
                markdown=message,
                payload=progress_payload,
            )
            next_status = after_progress(str(run["status"]))
            conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE id = ?", (next_status, _now(), run_id))
        plan = self.get_plan(run_id)
        self._notify_run(run_id)
        return {"success": True, "event_id": event["id"], "plan": plan, "run_status": next_status}

    def record_tool_trace(
        self,
        *,
        request_id: str,
        conversation_key: str,
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
            validation = self._validate_callback_conn(conn, request_id, conversation_key)
            if not validation["success"]:
                return validation
            run = validation["run"]
            run_id = int(run["id"])
            turn_ord = self._active_turn_ord_conn(conn, run_id)
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
                "turn_ord": turn_ord,
            }
            event = self._append_event_conn(
                conn,
                run_id=run_id,
                request_id=request_id,
                event_type="progress",
                title=title,
                markdown=markdown,
                payload=payload,
            )
            next_status = after_tool_trace(str(run["status"]))
            if next_status != run["status"]:
                conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE id = ?", (next_status, _now(), run_id))
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
        question: str,
        choices: list[str] | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key)
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
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                (after_user_question(str(run["status"])), _now(), run["id"]),
            )
        self._notify_run(int(run["id"]))
        return {"success": True, "event_id": event["id"], "question_id": event["id"]}

    def record_result(
        self,
        *,
        request_id: str,
        conversation_key: str,
        status: str,
        title: str,
        markdown: str,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if status not in VALID_RESULT_STATUSES:
            return {"success": False, "error": {"code": "invalid_status", "message": "status must be done, blocked, or failed."}}
        with self._lock, self._connect(immediate=True) as conn:
            validation = self._validate_callback_conn(conn, request_id, conversation_key)
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
                metadata = artifact.get("metadata") or {}
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
                        _json_dumps(metadata),
                        now,
                    ),
                )
            conn.execute(
                "UPDATE runs SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (status, now, now, run["id"]),
            )
        self._notify_run(int(run["id"]))
        return {"success": True, "run_status": status}

    def dismiss_run(self, run_id: int, *, note: str | None = None) -> dict[str, Any]:
        """Operator marks a non-terminal run finished when the agent never called record_result."""
        now = _now()
        with self._lock, self._connect(immediate=True) as conn:
            row = conn.execute(f"SELECT {RUN_PUBLIC_COLUMNS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"Run not found: {run_id}")
            run = _row_to_dict(row) or {}
            if run["status"] in TERMINAL_STATUSES:
                raise ValueError("Run is already terminal.")
            self._append_event_conn(
                conn,
                run_id=run_id,
                request_id="dashboard",
                event_type="system",
                title="Marked finished",
                markdown=note,
                payload={"reason": "operator_dismiss"},
            )
            conn.execute(
                "UPDATE runs SET status = 'done', completed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, run_id),
            )
        self._notify_run(run_id)
        return self.get_run(run_id)

    def list_events(self, run_id: int) -> list[dict[str, Any]]:
        """Relay callback/local trace events for a run."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, request_id, event_type, title, markdown, payload_json, created_at
                FROM events
                WHERE run_id = ?
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def list_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

    def list_runs_for_conversation(self, conversation_id: int) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT {RUN_PUBLIC_COLUMNS} FROM runs WHERE conversation_id = ? ORDER BY id DESC",
                (conversation_id,),
            ).fetchall()
        return [_row_to_dict(row) or {} for row in rows]

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
