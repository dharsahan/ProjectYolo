# Design Spec: Memory List Token Optimization

**Date:** 2026-05-02
**Topic:** Memory List Optimization
**Goal:** Prevent `model_max_prompt_tokens_exceeded` errors caused by `memory_list` dumping too much data into the LLM context window by switching to a summary-first approach.

## 1. Architecture & Concept
Currently, `memory_list` calls `memory.get_all()` which returns every raw memory (including full L2 conversational blobs), blowing up the context window.
The new approach will:
- Change `memory_list` to return a high-level summary of stored memory counts (e.g., number of L1, L2, L3, and L4 items).
- Instruct the agent to use the existing `search` mechanism (via prompt or a new `memory_search` tool) if they need to retrieve specific facts.
- Optionally return only the 10 most recent L3/L4 semantic/pattern memories, avoiding raw L2 conversational blobs entirely, keeping the token count extremely low.

## 2. Implementation in `tools/memory_ops.py`
- Modify `memory_list`:
  - Fetch counts from `TieredMemoryEngine.memory_stats()` instead of raw items.
  - Fetch only a limited subset of `L3_semantic_memory` and `L4_pattern_memory` using a direct query (or via engine extension if necessary) to avoid pulling raw `L2_episodic_memory` which contains massive conversational logs.
  - The return string will say: "Memory Summary: X working memories, Y raw events, Z semantic facts, W patterns. Recent facts: [List of top 10 L3/L4 items]. Use `memory_search` to find specific facts."

## 3. Implementation in `tools/yolo_memory.py`
- Expose a `get_recent_summary(user_id, limit=10)` method to `TieredMemoryEngine`. This method will return the latest `limit` semantic and pattern memories, completely ignoring raw L2 conversational blobs.

## 4. Agent Tool Updates
- Add a new `memory_search(query: str, user_id: int)` tool to `tools/memory_ops.py` (which calls `engine.search()`), so the agent can actively query the massive database instead of dumping it.
- Register `memory_search` in `tools/__init__.py`.

## 5. Security & Error Handling
- Ensures the agent cannot exceed context limits by accidentally dumping 193k tokens.
- FTS5 injection vulnerabilities are already mitigated in `engine.search()`.
