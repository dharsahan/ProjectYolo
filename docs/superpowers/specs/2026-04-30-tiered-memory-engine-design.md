# TieredMemoryEngine Design Specification

**Date:** 2026-04-30
**Topic:** TieredMemoryEngine Implementation
**Goal:** Replace the flat vector memory store with a 4-tier cognitive architecture using SQLite FTS5, featuring importance scoring, recency decay, and auto-consolidation.

## 1. Architecture: 4 Cognitive Tiers
All tiers reside in a new SQLite database (`yolo_memory.db`) using a Table-per-Tier schema.

- **L1: Working Memory:** A task-scoped key/value scratchpad. Wiped when the task completes.
- **L2: Episodic Memory:** Raw timestamped events. Auto-consolidated when a threshold is reached.
- **L3: Semantic Memory:** Distilled facts, preferences, and knowledge. Uses FTS5 for full-text search.
- **L4: Pattern Memory:** Inferred behavioral patterns.

## 2. Key Mechanisms

### 2.1 Importance Scoring (Hybrid Approach)
Every memory gets a heuristic score (0-10) before writing.
- **Heuristic Base:** Fast, predictable scoring using regex/weights based on category and length.
- **Explicit Tagging:** Agent can explicitly tag importance for a score boost.
- **Threshold:** Scores < 3 are discarded as noise.

### 2.2 Recency Decay
Retrieval Score = `importance × exp(-log(2) × days_old / 30)`.
Old memories are naturally down-ranked over time unless reinforced.

### 2.3 Contradiction Detection
Before writing L3 memories, the engine checks for conflicts (e.g., conflicting name claims or negated preferences) and resolves them in favor of newer facts.

### 2.4 Auto-Consolidation (Inline Sync)
When the L2 (Episodic) event count exceeds 20, an inline consolidation triggers during the agent turn:
- High-importance L2 events are promoted to L3 (Semantic).
- Recurring trends are inferred as L4 (Patterns).
- Processed L2 events are deleted.
- Manual trigger available via `consolidate_memories()`.

## 3. Structured Context Injection
The memory context injected into the system prompt (`prompt_builder.py`) is structured by tier:
- **L1 (Working):** Key-value pairs for the current task.
- **Core Identity:** High-importance personal facts.
- **L3 (Semantic):** Relevant categorized knowledge based on the current context.
- **L4 (Patterns):** Recognized behavioral trends.

## 4. Agent Tools
New tools added to `tools/memory_ops.py` and registered in `tools/__init__.py`:
- `working_memory_set(key, value)`
- `working_memory_get()`
- `working_memory_clear()`
- `consolidate_memories()`
- `memory_stats()`

## 5. Integration & Deployment
- **`tools/yolo_memory.py`:** Contains the new `TieredMemoryEngine` class (~500 lines).
- **`tools/memory_service.py`:** Updated to use `TieredMemoryEngine` by default.
- **`agent.py`:** `_build_memory_context()` updated to format the new structured context block.
- **Backwards Compatibility:** Legacy mem0/Qdrant support maintained as a fallback when `YOLO_MEM0_HYBRID=true`.
