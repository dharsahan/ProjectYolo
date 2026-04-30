# TieredMemoryEngine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat vector memory store with a 4-tier cognitive architecture using SQLite FTS5, featuring importance scoring, recency decay, and auto-consolidation.

**Architecture:** A new `TieredMemoryEngine` class in `tools/yolo_memory.py` handles SQLite FTS5 interactions. It is exposed to the agent via new tools in `tools/memory_ops.py`. `tools/memory_service.py` is updated to default to this engine while retaining hybrid mem0 support.

**Tech Stack:** Python 3, SQLite (sqlite3 with FTS5).

---

### Task 1: TieredMemoryEngine Database & Core Logic

**Files:**
- Create: `tools/yolo_memory.py`
- Test: `tests/test_tiered_memory.py`

- [ ] **Step 1: Write the failing test for DB initialization**

```python
# tests/test_tiered_memory.py
import pytest
from tools.yolo_memory import TieredMemoryEngine

def test_db_initialization(tmp_path):
    db_path = tmp_path / "test_memory.db"
    engine = TieredMemoryEngine(db_path=db_path)
    assert db_path.exists()
    
    # Check tables exist
    tables = engine.get_tables()
    assert "L1_working_memory" in tables
    assert "L2_episodic_memory" in tables
    assert "L3_semantic_memory" in tables
    assert "L4_pattern_memory" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tiered_memory.py::test_db_initialization -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Implement TieredMemoryEngine base class and schema**

```python
# tools/yolo_memory.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tiered_memory.py::test_db_initialization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/yolo_memory.py tests/test_tiered_memory.py
git commit -m "feat: add TieredMemoryEngine schema and initialization"
```

---

### Task 2: TieredMemoryEngine Working Memory & Scoring

**Files:**
- Modify: `tools/yolo_memory.py`
- Modify: `tests/test_tiered_memory.py`

- [ ] **Step 1: Write tests for Working Memory and Scoring**

```python
# Add to tests/test_tiered_memory.py
def test_working_memory(tmp_path):
    db_path = tmp_path / "test_memory.db"
    engine = TieredMemoryEngine(db_path=db_path)
    engine.working_memory_set(1, "current_goal", "Fix bug")
    
    mem = engine.working_memory_get(1)
    assert mem["current_goal"] == "Fix bug"
    
    engine.working_memory_clear(1)
    assert len(engine.working_memory_get(1)) == 0

def test_importance_scoring():
    engine = TieredMemoryEngine(db_path=":memory:")
    score_id = engine._score_importance("My name is Dharshan", "identity")
    assert score_id > 8.0
    
    score_low = engine._score_importance("ok", "fact")
    assert score_low < 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tiered_memory.py -k "test_working_memory or test_importance_scoring" -v`
Expected: FAIL

- [ ] **Step 3: Implement Working Memory and Scoring**

```python
# Add to tools/yolo_memory.py class TieredMemoryEngine:

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tiered_memory.py -k "test_working_memory or test_importance_scoring" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/yolo_memory.py tests/test_tiered_memory.py
git commit -m "feat: implement working memory layer and importance scoring"
```

---

### Task 3: Agent Tool Integrations

**Files:**
- Modify: `tools/memory_ops.py`
- Modify: `tools/__init__.py`

- [ ] **Step 1: Write tool wrappers in `tools/memory_ops.py`**

```python
# Add to tools/memory_ops.py
from tools.yolo_memory import TieredMemoryEngine
from tools.registry import register_tool

# Initialize a global instance
_tiered_engine = TieredMemoryEngine()

@register_tool()
def working_memory_set(key: str, value: str, user_id: int = 0) -> str:
    """Write a scratchpad note for the current task."""
    _tiered_engine.working_memory_set(user_id, key, value)
    return f"Working memory set: {key} = {value}"

@register_tool()
def working_memory_get(user_id: int = 0) -> str:
    """Read all working memory for the current task."""
    mem = _tiered_engine.working_memory_get(user_id)
    if not mem:
        return "Working memory is empty."
    return "\\n".join(f"{k}: {v}" for k, v in mem.items())

@register_tool()
def working_memory_clear(user_id: int = 0) -> str:
    """Wipe scratchpad after task completes."""
    _tiered_engine.working_memory_clear(user_id)
    return "Working memory cleared."
```

- [ ] **Step 2: Add tools to schema exports in `tools/__init__.py`**

Modify `tools/__init__.py` to import and export the new schemas.

```python
# Ensure imports exist in tools/__init__.py (if it explicitly lists them)
# e.g. from .memory_ops import working_memory_set, working_memory_get, working_memory_clear
```

- [ ] **Step 3: Commit**

```bash
git add tools/memory_ops.py tools/__init__.py
git commit -m "feat: add working memory tools for agent"
```

---

### Task 4: Service Layer and Context Formatting

**Files:**
- Modify: `tools/memory_service.py`
- Modify: `agent.py`

- [ ] **Step 1: Update `get_memory` in `memory_service.py`**

```python
# Modify tools/memory_service.py
import os
from tools.yolo_memory import TieredMemoryEngine

# Keep a reference to the active memory engine
_active_memory_engine = None

def get_memory():
    """Returns the memory engine instance based on configuration."""
    global _active_memory_engine
    if _active_memory_engine is None:
        if os.getenv("YOLO_MEMORY_ENGINE") == "mem0":
            from mem0 import Memory
            _active_memory_engine = Memory()
        else:
            _active_memory_engine = TieredMemoryEngine()
    return _active_memory_engine
```

- [ ] **Step 2: Modify `agent.py` to use `build_context`**

In `agent.py`, find `_build_memory_context` and update it to format the new L1-L4 blocks if the engine is `TieredMemoryEngine`.

```python
# In agent.py, inside run_agent_turn or prompt_builder:
# If using TieredMemoryEngine, fetch working memory and semantic memory to inject into prompt.
# Example modification (adjust to exact prompt_builder.py logic):
def _build_memory_context(user_id: int):
    from tools.memory_service import get_memory
    from tools.yolo_memory import TieredMemoryEngine
    
    memory = get_memory()
    if isinstance(memory, TieredMemoryEngine):
        working_mem = memory.working_memory_get(user_id)
        wm_str = "\\n".join(f"- {k}: {v}" for k,v in working_mem.items()) if working_mem else "None"
        
        return f"[MEMORY_CONTEXT]\\n## Working memory\\n{wm_str}\\n[/MEMORY_CONTEXT]"
    else:
        # Legacy mem0 logic
        return "Legacy Memory..."
```

- [ ] **Step 3: Commit**

```bash
git add tools/memory_service.py agent.py
git commit -m "feat: integrate TieredMemoryEngine into prompt context generation"
```
