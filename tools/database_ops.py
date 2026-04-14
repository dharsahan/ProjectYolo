import json
import sqlite3
from pathlib import Path

from tools.base import YOLO_HOME

DB_PATH = YOLO_HOME / "yolo_v2.db"
_CONNECTION_TIMEOUT_SECONDS = 10


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=_CONNECTION_TIMEOUT_SECONDS)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column_exists(
    conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str
) -> None:
    existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in existing_columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

def init_db():
    """Initialize the global Yolo database."""
    with _connect() as conn:
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

        conn.commit()

def add_cron(user_id: int, task_description: str, interval_minutes: int):
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be greater than 0")

    with _connect() as conn:
        cursor = conn.cursor()
        # Set next_run to now + interval
        cursor.execute("""
            INSERT INTO crons (user_id, task_description, interval_minutes, next_run)
            VALUES (?, ?, ?, datetime('now', '+' || ? || ' minutes'))
        """, (user_id, task_description, interval_minutes, interval_minutes))
        conn.commit()

def get_due_crons():
    with _connect() as conn:
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

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE crons 
            SET last_run = CURRENT_TIMESTAMP, 
                next_run = datetime('now', '+' || ? || ' minutes')
            WHERE cron_id = ?
        """, (interval_minutes, cron_id))
        conn.commit()

def list_crons(user_id: int):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cron_id, task_description, next_run FROM crons WHERE user_id = ? AND active = 1 ORDER BY next_run ASC",
            (user_id,),
        )
        return cursor.fetchall()

def delete_cron(cron_id: int):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE crons SET active = 0 WHERE cron_id = ?", (cron_id,))
        conn.commit()
        return cursor.rowcount > 0

def save_session(
    user_id: int,
    history: list,
    yolo_mode: bool,
    think_mode: bool = False,
    think_mode_policy: str = "auto",
    pending_confirmation: dict | None = None,
):
    pending_confirmation_json = (
        json.dumps(pending_confirmation) if pending_confirmation is not None else None
    )

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (user_id, history, yolo_mode, think_mode, think_mode_policy, pending_confirmation, last_active)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                history=excluded.history,
                yolo_mode=excluded.yolo_mode,
                think_mode=excluded.think_mode,
                think_mode_policy=excluded.think_mode_policy,
                pending_confirmation=excluded.pending_confirmation,
                last_active=CURRENT_TIMESTAMP
        """, (
            user_id,
            json.dumps(history),
            yolo_mode,
            think_mode,
            think_mode_policy,
            pending_confirmation_json,
        ))
        conn.commit()

def load_session(user_id: int):
    with _connect() as conn:
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

            pending_confirmation = None
            if row[4]:
                try:
                    pending_confirmation = json.loads(row[4])
                except json.JSONDecodeError:
                    pending_confirmation = None

            raw_policy = str(row[3] or "").strip().lower()
            if raw_policy not in {"auto", "force_on", "force_off"}:
                raw_policy = "force_on" if bool(row[2]) else "auto"

            return history, bool(row[1]), bool(row[2]), raw_policy, pending_confirmation
        return None, None, None, None, None

def add_background_task(task_id: str, user_id: int, objective: str):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO background_tasks (task_id, user_id, objective, status)
            VALUES (?, ?, ?, 'running')
        """, (task_id, user_id, objective))
        conn.commit()

def update_background_task(task_id: str, status: str, result: str):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE background_tasks SET status = ?, result = ? WHERE task_id = ?
        """, (status, result, task_id))
        conn.commit()

def get_pending_notifications():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, user_id, objective, status, result 
            FROM background_tasks 
            WHERE status IN ('completed', 'failed') AND notified = 0
        """)
        return cursor.fetchall()

def mark_notified(task_id: str):
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE background_tasks SET notified = 1 WHERE task_id = ?", (task_id,))
        conn.commit()
