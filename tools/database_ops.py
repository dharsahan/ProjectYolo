import json
import sqlite3
import threading

from tools.base import YOLO_HOME

DB_PATH = YOLO_HOME / "yolo_v2.db"
_CONNECTION_TIMEOUT_SECONDS = 10

# Persistent shared connection (WAL mode allows safe concurrent reads/writes).
# A single connection avoids repeated open/close overhead on hot paths
# (notification worker every 10s, cron every 60s, every save_session call).
_conn_lock = threading.Lock()
_shared_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _shared_conn
    with _conn_lock:
        if _shared_conn is None:
            conn = sqlite3.connect(
                DB_PATH,
                timeout=_CONNECTION_TIMEOUT_SECONDS,
                check_same_thread=False,
                isolation_level=None,  # autocommit; we manage transactions explicitly
            )
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA temp_store = MEMORY")
            _shared_conn = conn
        return _shared_conn


class _ConnContext:
    """Context manager wrapper that does NOT close the shared connection."""

    def __init__(self) -> None:
        self.conn = _connect()

    def __enter__(self) -> sqlite3.Connection:
        _conn_lock.acquire()
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            _conn_lock.release()


def _conn_ctx() -> _ConnContext:
    return _ConnContext()


def _ensure_column_exists(
    conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str
) -> None:
    existing_columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")
    }
    if column_name not in existing_columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def init_db():
    """Initialize the global Yolo database."""
    with _conn_ctx() as conn:
        cursor = conn.cursor()

        # Sessions Table: Stores persistent conversation history and flags
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id INTEGER PRIMARY KEY,
                history TEXT,
                yolo_mode BOOLEAN,
                think_mode BOOLEAN,
                think_mode_policy TEXT,
                pending_confirmation TEXT,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Background Tasks Table: Tracks long-running autonomous missions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS background_tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER,
                objective TEXT,
                status TEXT,
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified BOOLEAN DEFAULT 0
            )
        """)

        # Crons Table: Stores recurring scheduled tasks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crons (
                cron_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_description TEXT,
                interval_minutes INTEGER,
                last_run TIMESTAMP,
                next_run TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        """)

        # Lightweight migration for existing databases.
        _ensure_column_exists(conn, "sessions", "think_mode", "BOOLEAN")
        _ensure_column_exists(conn, "sessions", "think_mode_policy", "TEXT")
        _ensure_column_exists(conn, "sessions", "pending_confirmation", "TEXT")


def add_cron(user_id: int, task_description: str, interval_minutes: int):
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be greater than 0")

    with _conn_ctx() as conn:
        cursor = conn.cursor()
        # Set next_run to now + interval
        cursor.execute(
            """
            INSERT INTO crons (user_id, task_description, interval_minutes, next_run)
            VALUES (?, ?, ?, datetime('now', '+' || ? || ' minutes'))
        """,
            (user_id, task_description, interval_minutes, interval_minutes),
        )


def get_due_crons():
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cron_id, user_id, task_description, interval_minutes 
            FROM crons 
            WHERE active = 1 AND (next_run IS NULL OR next_run <= CURRENT_TIMESTAMP)
            ORDER BY next_run ASC
        """)
        return cursor.fetchall()


def update_cron_run(cron_id: int, interval_minutes: int):
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be greater than 0")

    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE crons 
            SET last_run = CURRENT_TIMESTAMP, 
                next_run = datetime('now', '+' || ? || ' minutes')
            WHERE cron_id = ?
        """,
            (interval_minutes, cron_id),
        )


def list_crons(user_id: int):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cron_id, task_description, next_run FROM crons WHERE user_id = ? AND active = 1 ORDER BY next_run ASC",
            (user_id,),
        )
        return cursor.fetchall()


def delete_cron(cron_id: int):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE crons SET active = 0 WHERE cron_id = ?", (cron_id,))
        return cursor.rowcount > 0


def save_session(
    user_id: int,
    history: list,
    yolo_mode: bool,
    think_mode: bool = False,
    think_mode_policy: str = "auto",
    pending_confirmations: list | None = None,
):
    pending_confirmations_json = (
        json.dumps(pending_confirmations) if pending_confirmations is not None else None
    )

    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (user_id, history, yolo_mode, think_mode, think_mode_policy, pending_confirmation, last_active)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                history=excluded.history,
                yolo_mode=excluded.yolo_mode,
                think_mode=excluded.think_mode,
                think_mode_policy=excluded.think_mode_policy,
                pending_confirmation=excluded.pending_confirmation,
                last_active=CURRENT_TIMESTAMP
        """,
            (
                user_id,
                json.dumps(history),
                yolo_mode,
                think_mode,
                think_mode_policy,
                pending_confirmations_json,
            ),
        )


def load_session(user_id: int):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT history, yolo_mode, think_mode, think_mode_policy, pending_confirmation FROM sessions WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            try:
                history = json.loads(row[0]) if row[0] else []
            except json.JSONDecodeError:
                history = []

            pending_confirmations = []
            if row[4]:
                try:
                    pending_confirmations = json.loads(row[4])
                except json.JSONDecodeError:
                    pending_confirmations = []

            raw_policy = str(row[3] or "").strip().lower()
            if raw_policy not in {"auto", "force_on", "force_off"}:
                raw_policy = "force_on" if bool(row[2]) else "auto"

            return (
                history,
                bool(row[1]),
                bool(row[2]),
                raw_policy,
                pending_confirmations,
            )
        return None, None, None, None, None


def add_background_task(task_id: str, user_id: int, objective: str):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO background_tasks (task_id, user_id, objective, status)
            VALUES (?, ?, ?, 'running')
        """,
            (task_id, user_id, objective),
        )


def update_background_task(task_id: str, status: str, result: str):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE background_tasks SET status = ?, result = ? WHERE task_id = ?
        """,
            (status, result, task_id),
        )


def get_pending_notifications():
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, user_id, objective, status, result 
            FROM background_tasks 
            WHERE status IN ('completed', 'failed') AND notified = 0
        """)
        return cursor.fetchall()


def mark_notified(task_id: str):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE background_tasks SET notified = 1 WHERE task_id = ?", (task_id,)
        )


def list_background_tasks(user_id: int, limit: int = 5):
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT task_id, objective, status, created_at 
            FROM background_tasks 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """,
            (user_id, limit),
        )
        return cursor.fetchall()
