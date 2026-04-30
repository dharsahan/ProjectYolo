import sqlite3
import os
from pathlib import Path
from tools.base import YOLO_HOME

class TieredMemoryEngine:
    def __init__(self, db_path=None):
        self.db_path = db_path or (YOLO_HOME / "yolo_memory.db")
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS L1_working_memory (
                    user_id INTEGER,
                    key TEXT,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, key)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS L2_episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    event TEXT,
                    importance REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS L3_semantic_memory USING fts5(
                    user_id UNINDEXED,
                    fact,
                    category UNINDEXED,
                    importance UNINDEXED,
                    created_at UNINDEXED,
                    updated_at UNINDEXED
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS L4_pattern_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    pattern TEXT,
                    confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return [row['name'] for row in cursor.fetchall()]

    def working_memory_set(self, user_id: int, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO L1_working_memory (user_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, created_at=CURRENT_TIMESTAMP
            """, (user_id, key, value))
            conn.commit()

    def working_memory_get(self, user_id: int) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM L1_working_memory WHERE user_id = ?", (user_id,))
            return {row['key']: row['value'] for row in cursor.fetchall()}

    def working_memory_clear(self, user_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM L1_working_memory WHERE user_id = ?", (user_id,))
            conn.commit()

    def _score_importance(self, text: str, category: str) -> float:
        # Simple heuristic hybrid scoring
        score = 5.0
        text_lower = text.lower()
        if category == "identity" or "my name is" in text_lower:
            score += 4.0
        elif category == "preference" or "always" in text_lower or "never" in text_lower:
            score += 3.0
        
        if len(text) < 5 and category not in ["identity", "preference"]:
            score -= 4.0
            
        return min(max(score, 0.0), 10.0)

    def add(self, fact: str, user_id: str):
        uid = int(user_id)
        importance = self._score_importance(fact, "fact")
        if importance < 3.0:
            return  # Noise
            
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO L2_episodic_memory (user_id, event, importance)
                VALUES (?, ?, ?)
            """, (uid, fact, importance))
            
            # Check threshold
            cursor.execute("SELECT count(*) FROM L2_episodic_memory WHERE user_id = ?", (uid,))
            count = cursor.fetchone()[0]
            conn.commit()

        if count > 20:
            self.consolidate_memories(uid)

    def consolidate_memories(self, user_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, event, importance FROM L2_episodic_memory WHERE user_id = ?", (user_id,))
            events = cursor.fetchall()
            for row in events:
                if row['importance'] >= 3.0:
                    cursor.execute("""
                        INSERT INTO L3_semantic_memory (user_id, fact, category, importance, created_at, updated_at)
                        VALUES (?, ?, 'fact', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (user_id, row['event'], row['importance']))
            cursor.execute("DELETE FROM L2_episodic_memory WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_all(self, filters: dict = None) -> list:
        uid = int(filters.get("user_id", 0)) if filters else 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Fetch from L3 and L2
            cursor.execute("SELECT rowid, fact FROM L3_semantic_memory WHERE user_id = ?", (uid,))
            l3_memories = [{"id": f"l3_{row['rowid']}", "memory": row['fact']} for row in cursor.fetchall()]
            
            cursor.execute("SELECT id, event FROM L2_episodic_memory WHERE user_id = ?", (uid,))
            l2_memories = [{"id": f"l2_{row['id']}", "memory": row['event']} for row in cursor.fetchall()]
            
            return l3_memories + l2_memories

    def search(self, query: str, filters: dict = None, limit: int = 8) -> list:
        uid = int(filters.get("user_id", 0)) if filters else 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Basic FTS5 search
            safe_query = query.replace('"', '""')
            try:
                cursor.execute(f"""
                    SELECT fact FROM L3_semantic_memory 
                    WHERE user_id = ? AND L3_semantic_memory MATCH '"{safe_query}"'
                    LIMIT ?
                """, (uid, limit))
                return [{"memory": row['fact']} for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                # Fallback to get_all if FTS parsing fails
                return self.get_all(filters)[:limit]

    def delete(self, memory_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if memory_id.startswith("l3_"):
                rowid = int(memory_id[3:])
                cursor.execute("DELETE FROM L3_semantic_memory WHERE rowid = ?", (rowid,))
            elif memory_id.startswith("l2_"):
                eid = int(memory_id[3:])
                cursor.execute("DELETE FROM L2_episodic_memory WHERE id = ?", (eid,))
            conn.commit()

    def delete_all(self, user_id: str):
        uid = int(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM L1_working_memory WHERE user_id = ?", (uid,))
            cursor.execute("DELETE FROM L2_episodic_memory WHERE user_id = ?", (uid,))
            cursor.execute("DELETE FROM L3_semantic_memory WHERE user_id = ?", (uid,))
            cursor.execute("DELETE FROM L4_pattern_memory WHERE user_id = ?", (uid,))
            conn.commit()
