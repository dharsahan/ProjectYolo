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
        text_lower = text.lower().strip()
        if category == "identity" or text_lower.startswith("my name is") or text_lower.startswith("i am"):
            score += 4.0
        elif category == "preference" or " always " in text_lower or " never " in text_lower:
            score += 3.0
        
        if len(text) < 5 and category not in ["identity", "preference"]:
            score -= 4.0
            
        return min(max(score, 0.0), 10.0)

    def add(self, fact, user_id: str = None, category: str = "fact", **kwargs):
        import re
        if user_id is None:
            user_id = kwargs.get("user_id", "0")
        uid = int(user_id)
        
        if isinstance(fact, list):
            text_parts = []
            for msg in fact:
                if isinstance(msg, dict) and "content" in msg and "role" in msg:
                    content = msg["content"]
                    if msg["role"] == "assistant":
                        content = re.sub(r"<thought>.*?</thought>", "", content, flags=re.DOTALL).strip()
                    if content:
                        text_parts.append(f"{msg['role']}: {content}")
            fact_str = "\n".join(text_parts)
        elif isinstance(fact, dict) and "content" in fact:
            fact_str = fact["content"]
        else:
            fact_str = str(fact)
            
        importance = self._score_importance(fact_str, category)
        if importance < 3.0:
            return  # Noise
            
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("""
                INSERT INTO L2_episodic_memory (user_id, event, importance)
                VALUES (?, ?, ?)
            """, (uid, fact_str, importance))
            
            # Check threshold
            cursor.execute("SELECT count(*) FROM L2_episodic_memory WHERE user_id = ?", (uid,))
            count = cursor.fetchone()[0]
            if count > 20:
                self._consolidate_internal(cursor, uid)
            conn.commit()

    def consolidate_memories(self, user_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            self._consolidate_internal(cursor, user_id)
            conn.commit()

    def _consolidate_internal(self, cursor, user_id: int):
        cursor.execute("SELECT id, event, importance FROM L2_episodic_memory WHERE user_id = ?", (user_id,))
        events = cursor.fetchall()
        for row in events:
            if row['importance'] >= 3.0:
                # Prevent duplicates in L3
                cursor.execute("SELECT rowid FROM L3_semantic_memory WHERE user_id = ? AND fact = ?", (user_id, row['event']))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO L3_semantic_memory (user_id, fact, category, importance, created_at, updated_at)
                        VALUES (?, ?, 'fact', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (user_id, row['event'], row['importance']))
                    
                # Infer patterns into L4
                event_lower = row['event'].lower()
                if row['importance'] >= 6.0 and ("always" in event_lower or "never" in event_lower or "prefers" in event_lower):
                    cursor.execute("SELECT id FROM L4_pattern_memory WHERE user_id = ? AND pattern = ?", (user_id, row['event']))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO L4_pattern_memory (user_id, pattern, confidence)
                            VALUES (?, ?, ?)
                        """, (user_id, row['event'], row['importance']))

        cursor.execute("DELETE FROM L2_episodic_memory WHERE user_id = ?", (user_id,))

    def memory_stats(self, user_id: int) -> dict:
        stats = {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM L1_working_memory WHERE user_id = ?", (user_id,))
            stats['L1_working_memory'] = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM L2_episodic_memory WHERE user_id = ?", (user_id,))
            stats['L2_episodic_memory'] = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM L3_semantic_memory WHERE user_id = ?", (user_id,))
            stats['L3_semantic_memory'] = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM L4_pattern_memory WHERE user_id = ?", (user_id,))
            stats['L4_pattern_memory'] = cursor.fetchone()[0]
        return stats

    def get_all(self, filters: dict = None) -> list:
        uid = int(filters.get("user_id", 0)) if filters else 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Fetch from L3 and L2
            cursor.execute("SELECT rowid, fact FROM L3_semantic_memory WHERE user_id = ?", (uid,))
            l3_memories = [{"id": f"l3_{row['rowid']}", "memory": row['fact']} for row in cursor.fetchall()]
            
            cursor.execute("SELECT id, event FROM L2_episodic_memory WHERE user_id = ?", (uid,))
            l2_memories = [{"id": f"l2_{row['id']}", "memory": row['event']} for row in cursor.fetchall()]
            
            cursor.execute("SELECT key, value FROM L1_working_memory WHERE user_id = ?", (uid,))
            l1_memories = [{"id": f"l1_{row['key']}", "memory": f"{row['key']}: {row['value']}"} for row in cursor.fetchall()]
            
            cursor.execute("SELECT id, pattern FROM L4_pattern_memory WHERE user_id = ?", (uid,))
            l4_memories = [{"id": f"l4_{row['id']}", "memory": row['pattern']} for row in cursor.fetchall()]
            
            return l3_memories + l2_memories + l1_memories + l4_memories

    def search(self, query: str, filters: dict = None, limit: int = 8) -> list:
        import datetime
        import math
        import re
        uid = int(filters.get("user_id", 0)) if filters else 0
        
        # Tokenize query for better matching, keep standard words, escape FTS5 special chars
        safe_query = re.sub(r'[^\w\s]', ' ', query)
        terms = [t.strip() for t in safe_query.split() if len(t.strip()) >= 2]
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            raw_results = []
            
            if terms:
                fts_query = " OR ".join(terms)
                like_queries = [f"%{t}%" for t in terms]
                
                try:
                    cursor.execute(f"""
                        SELECT rowid, fact, importance, created_at FROM L3_semantic_memory 
                        WHERE user_id = ? AND L3_semantic_memory MATCH ?
                    """, (uid, fts_query))
                    raw_results.extend([{"id": f"l3_{row['rowid']}", "memory": row['fact'], "importance": row['importance'] or 5.0, "created_at": row['created_at']} for row in cursor.fetchall()])
                except sqlite3.OperationalError as e:
                    # Log the FTS5 error silently
                    pass
                    
                # Search L2 with LIKE
                where_clause = " OR ".join(["event LIKE ?"] * len(like_queries))
                cursor.execute(f"""
                    SELECT id, event, importance, created_at FROM L2_episodic_memory 
                    WHERE user_id = ? AND ({where_clause})
                """, [uid] + like_queries)
                raw_results.extend([{"id": f"l2_{row['id']}", "memory": row['event'], "importance": row['importance'] or 5.0, "created_at": row['created_at']} for row in cursor.fetchall()])
                
                # Search L4 with LIKE
                where_clause_l4 = " OR ".join(["pattern LIKE ?"] * len(like_queries))
                cursor.execute(f"""
                    SELECT id, pattern, confidence, created_at FROM L4_pattern_memory 
                    WHERE user_id = ? AND ({where_clause_l4})
                """, [uid] + like_queries)
                raw_results.extend([{"id": f"l4_{row['id']}", "memory": row['pattern'], "importance": row['confidence'] or 5.0, "created_at": row['created_at']} for row in cursor.fetchall()])
            
            if not raw_results:
                return []
                
            # Apply recency decay: score = importance * exp(-ln(2) * days_old / 30)
            now = datetime.datetime.now()
            scored_results = []
            for r in raw_results:
                try:
                    created_at = datetime.datetime.strptime(r['created_at'], '%Y-%m-%d %H:%M:%S')
                    days_old = (now - created_at).days
                    if days_old < 0:
                        days_old = 0
                except Exception:
                    days_old = 0
                
                decay = math.exp(-math.log(2) * days_old / 30.0)
                final_score = float(r['importance']) * decay
                scored_results.append((final_score, r))
                
            scored_results.sort(key=lambda x: x[0], reverse=True)
            
            seen = set()
            final_list = []
            for _, r in scored_results:
                if r['memory'] not in seen:
                    seen.add(r['memory'])
                    final_list.append({"id": r["id"], "memory": r['memory']})
                    if len(final_list) >= limit:
                        break
                        
            return final_list

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
            
            cursor.execute("SELECT rowid FROM L3_semantic_memory WHERE user_id = ?", (uid,))
            rowids = [row[0] for row in cursor.fetchall()]
            for rid in rowids:
                cursor.execute("DELETE FROM L3_semantic_memory WHERE rowid = ?", (rid,))
                
            cursor.execute("DELETE FROM L4_pattern_memory WHERE user_id = ?", (uid,))
            conn.commit()
