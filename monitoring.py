import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tools.base import YOLO_HOME

DB_PATH = YOLO_HOME / "yolo_v2.db"


def _read_last_agent_log_line() -> str:
    log_path = YOLO_HOME / "agent_log.txt"
    if not log_path.exists():
        return ""

    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return ""
            offset = min(size, 4096)
            f.seek(-offset, os.SEEK_END)
            chunk = f.read().decode("utf-8", errors="replace")
        lines = [line for line in chunk.splitlines() if line.strip()]
        return lines[-1] if lines else ""
    except Exception:
        return ""


def build_health_payload(session=None) -> dict:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "pending_background_notifications": 0,
        "running_background_tasks": 0,
        "active_crons": 0,
        "next_cron_run": None,
        "last_agent_log_entry": _read_last_agent_log_line(),
        "llm_provider": os.getenv("LLM_PROVIDER", "auto"),
        "model_name": os.getenv("MODEL_NAME", ""),
        "total_tokens": 0,
    }

    if session:
        payload["total_tokens"] = getattr(session, "total_tokens", 0)

    if not DB_PATH.exists():
        return payload

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT COUNT(*) FROM background_tasks WHERE status IN ('completed','failed') AND notified = 0"
            )
            payload["pending_background_notifications"] = int(cursor.fetchone()[0])

            cursor.execute(
                "SELECT COUNT(*) FROM background_tasks WHERE status = 'running'"
            )
            payload["running_background_tasks"] = int(cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM crons WHERE active = 1")
            payload["active_crons"] = int(cursor.fetchone()[0])

            cursor.execute(
                "SELECT next_run FROM crons WHERE active = 1 ORDER BY next_run ASC LIMIT 1"
            )
            row = cursor.fetchone()
            payload["next_cron_run"] = row[0] if row else None
    except Exception as e:
        payload["db_error"] = str(e)

    return payload
