# Memory List Token Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent token overflow errors by modifying `memory_list` to return a high-level summary and introducing a `memory_search` tool for targeted retrieval.

**Architecture:** We will add a `get_recent_summary` method to `TieredMemoryEngine`. Then, we will rewrite `memory_list` in `tools/memory_ops.py` to fetch tier stats and the recent summary instead of dumping all memories. Finally, we will introduce and register a `memory_search` tool to allow the agent to query the FTS5 database directly.

**Tech Stack:** Python 3, SQLite.

---

### Task 1: Add `get_recent_summary` to `TieredMemoryEngine`

**Files:**
- Modify: `tools/yolo_memory.py`
- Modify: `tests/test_tiered_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_tiered_memory.py
def test_get_recent_summary():
    from tools.yolo_memory import TieredMemoryEngine
    engine = TieredMemoryEngine(db_path=":memory:")
    
    # Add an episodic memory
    engine.add("I had a great day today.", "1")
    
    # Add a semantic fact
    engine.add("My favorite color is blue.", "1", category="preference")
    engine.consolidate_memories(1)
    
    summary = engine.get_recent_summary(user_id=1, limit=5)
    
    # Should only contain the semantic memory (L3/L4), not the L2 blob
    assert len(summary) == 1
    assert "blue" in summary[0]["memory"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && PYTHONPATH=. pytest tests/test_tiered_memory.py::test_get_recent_summary -v`
Expected: FAIL with `AttributeError: 'TieredMemoryEngine' object has no attribute 'get_recent_summary'`

- [ ] **Step 3: Implement `get_recent_summary`**

```python
# In tools/yolo_memory.py, add the following method to TieredMemoryEngine:
    def get_recent_summary(self, user_id: int, limit: int = 10) -> list:
        """Returns the most recent L3 (semantic) and L4 (pattern) memories, ignoring raw L2 events."""
        uid = int(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Fetch from L3
            cursor.execute("""
                SELECT rowid, fact, created_at FROM L3_semantic_memory 
                WHERE user_id = ? 
                ORDER BY created_at DESC LIMIT ?
            """, (uid, limit))
            l3_memories = [{"id": f"l3_{row['rowid']}", "memory": row['fact'], "created_at": row['created_at']} for row in cursor.fetchall()]
            
            # Fetch from L4
            cursor.execute("""
                SELECT id, pattern, created_at FROM L4_pattern_memory 
                WHERE user_id = ? 
                ORDER BY created_at DESC LIMIT ?
            """, (uid, limit))
            l4_memories = [{"id": f"l4_{row['id']}", "memory": row['pattern'], "created_at": row['created_at']} for row in cursor.fetchall()]
            
            combined = l3_memories + l4_memories
            
            # Sort by created_at descending
            combined.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            # Return top N
            return combined[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && PYTHONPATH=. pytest tests/test_tiered_memory.py::test_get_recent_summary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/yolo_memory.py tests/test_tiered_memory.py
git commit -m "feat: add get_recent_summary method to TieredMemoryEngine"
```

---

### Task 2: Rewrite `memory_list` and Add `memory_search`

**Files:**
- Modify: `tools/memory_ops.py`
- Modify: `tools/__init__.py`

- [ ] **Step 1: Rewrite `memory_list` and add `memory_search`**

```python
# In tools/memory_ops.py, replace the memory_list function and add memory_search
@register_tool()
def memory_list(user_id: int) -> str:
    """Get a high-level summary of stored memories. Does NOT return all memories. Use memory_search for targeted queries."""
    try:
        memory = get_memory()
        
        if isinstance(memory, TieredMemoryEngine):
            stats = memory.memory_stats(user_id)
            recent = memory.get_recent_summary(user_id, limit=10)
            
            output = "### Memory Summary\n"
            output += f"Working Memory (L1): {stats.get('L1_working_memory', 0)} items\n"
            output += f"Raw Conversational Events (L2): {stats.get('L2_episodic_memory', 0)} items\n"
            output += f"Semantic Facts (L3): {stats.get('L3_semantic_memory', 0)} items\n"
            output += f"Behavioral Patterns (L4): {stats.get('L4_pattern_memory', 0)} items\n\n"
            
            output += "### Top 10 Most Recent Facts & Patterns:\n"
            if not recent:
                output += "No facts stored yet.\n"
            else:
                for m in recent:
                    output += f"- `{m['id']}`: {m['memory']}\n"
            
            output += "\n*Note: To find specific facts or past conversations, use the `memory_search` tool.*"
            audit_log("memory_list", {"user_id": user_id}, "success")
            return output
        else:
            # Fallback for old mem0 flat system
            results = memory.get_all(filters={"user_id": str(user_id)})
            if isinstance(results, dict) and "results" in results:
                results = results["results"]

            if not results:
                return "No memories found for your profile."
            
            # Truncate fallback to prevent overflow just in case
            output = f"### Your Long-Term Memories (Showing top 20 of {len(results)}):\n\n"
            for m in results[:20]:
                if isinstance(m, dict):
                    text = m.get("memory") or m.get("text") or str(m)
                    mem_id = m.get("id") or m.get("memory_id") or "unknown"
                else:
                    text = str(m)
                    mem_id = "unknown"
                output += f"- `{mem_id}`: {text}\n"

            output += "\n*Note: Use `memory_search` to query for specific keywords.*"
            audit_log("memory_list", {"user_id": user_id}, "success")
            return output
            
    except Exception as e:
        audit_log("memory_list", {"user_id": user_id}, "error", str(e))
        return f"Error listing memories: {e}"

@register_tool()
def memory_search(query: str, user_id: int) -> str:
    """Semantic search the permanent memory database for a specific keyword or question."""
    try:
        memory = get_memory()
        results = memory.search(query, filters={"user_id": str(user_id)}, limit=10)
        
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
            
        if not results:
            return f"No memories found matching: '{query}'"
            
        output = f"### Search Results for '{query}':\n\n"
        for m in results:
            if isinstance(m, dict):
                text = m.get("memory") or m.get("text") or str(m)
                mem_id = m.get("id") or m.get("memory_id") or "unknown"
            else:
                text = str(m)
                mem_id = "unknown"
            output += f"- `{mem_id}`: {text}\n"
            
        audit_log("memory_search", {"user_id": user_id, "query": query}, "success")
        return output
    except Exception as e:
        audit_log("memory_search", {"user_id": user_id, "query": query}, "error", str(e))
        return f"Error searching memories: {e}"
```

- [ ] **Step 2: Update `tools/__init__.py` schemas**

```python
# In tools/__init__.py, update __all__ and imports:
# Add memory_search to the imports from tools.memory_ops
# Add "memory_search" to __all__

# In TOOLS_SCHEMAS, add the schema for memory_search and update memory_list description
    {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "Get a high-level summary of stored memory counts and the 10 most recent facts. Does NOT return all memories.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Semantic search the permanent memory database for a specific keyword or question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, e.g., 'What is my name?' or 'TypeScript'",
                    }
                },
                "required": ["query"],
            },
        },
    },
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

Run: `source .venv/bin/activate && PYTHONPATH=. pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tools/memory_ops.py tools/__init__.py
git commit -m "feat: optimize memory_list token usage and add memory_search tool"
```
