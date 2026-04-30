# Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 12 key improvements across the codebase to enhance test coverage, modularity, cache management, and error handling.

**Architecture:** This refactoring plan addresses critical tech-debt incrementally across 12 isolated phases, ensuring system stability is maintained at each step.

**Tech Stack:** Python, asyncio, SQLite.

---

### Task 1: Fix `audit_log` Silently Swallows All Exceptions (Phase 1)

**Files:**
- Modify: `tools/base.py`

- [x] **Step 1: Write the minimal implementation**

Update `audit_log` to report failures to `sys.stderr`.

### Task 2: Fix `background_ops.py` Untracked `asyncio` Tasks (Phase 2)

**Files:**
- Modify: `tools/background_ops.py`

- [x] **Step 1: Write the minimal implementation**

Create a global `_background_tasks = set()` and attach tasks to it with `task.add_done_callback(_background_tasks.discard)`.

### Task 3: Fix `SessionManager.save` Object Identity Issue (Phase 3)

**Files:**
- Modify: `session.py`

- [x] **Step 1: Write the minimal implementation**

Update `SessionManager.save` to use `hash(json.dumps(last_msg, sort_keys=True))` instead of `id(last_msg)`.

### Task 4: Fix `get_mem0_config` Always Uses OpenAI (Phase 4)

**Files:**
- Modify: `tools/base.py`

- [ ] **Step 1: Write the minimal implementation**
Respect the active provider configuration in the embeddings setup.

### Task 5: Fix `_PROMPT_TEMPLATE_CACHE` Is Never Invalidated (Phase 5)

**Files:**
- Modify: `agent.py`

- [x] **Step 1: Write the minimal implementation**
Implement cache invalidation or a timestamp check.

### Task 6: Make `run_worker_loop` Limits Configurable (Phase 6)

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Write the minimal implementation**
Read configurable limits from environment variables.

### Task 7: Replace Brittle Keyword Matching in Intent Detection (Phase 7)

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Write the minimal implementation**
Improve `_is_complex_task_prompt` and related functions.

### Task 8: Add Retry Logic for Rate Limits in `LLMRouter` (Phase 8)

**Files:**
- Modify: `llm_router.py`

- [ ] **Step 1: Write the minimal implementation**
Implement exponential backoff.

### Task 9: Improve Database Migration Strategy (Phase 9)

**Files:**
- Modify: `tools/database_ops.py`

- [x] **Step 1: Write the minimal implementation**
Introduce versioned migrations.

### Task 10: Refactor `execute_tool_direct` Hardcoded Table (Phase 10)

**Files:**
- Modify: `agent.py`, tools modules

- [x] **Step 1: Write the minimal implementation**
Implement a decorator-based tool registry.

### Task 11: Split `agent.py` to Respect Single Responsibility (Phase 11)

**Files:**
- Modify: `agent.py`, `prompt_builder.py`, `tool_dispatcher.py`, `worker.py`

- [x] **Step 1: Write the minimal implementation**
Extract prompt and worker logic into separate files.

### Task 12: Add Comprehensive Test Coverage (Phase 12)

**Files:**
- Modify: `tests/`

- [x] **Step 1: Write the minimal implementation**
Add unit and integration tests for tools and core modules.
