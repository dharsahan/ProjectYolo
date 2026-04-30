# Project Yolo Architectural Analysis

## 1. Core Orchestration (The Brain)

Project Yolo's core is a modular orchestration loop that separates reasoning, communication, prompting, and execution.

### Components

- **`agent.py` (Orchestrator)**
  - **Function:** The central heartbeat of the system.
  - **Key Logic:** `run_agent_turn` manages the `Session` state, triggers prompt builds, calls the LLM, and orchestrates parallel tool execution.
  - **Advanced Features:** Supports 'Think Mode', 'Self-Upgrade' phases, and 'Experience Updates'.

- **`llm_router.py` (LLM Abstraction)**
  - **Function:** Provides a unified interface for multiple LLM providers (OpenAI, OpenRouter, Anthropic).
  - **Key Logic:** `LLMRouter` handles model selection and implements exponential backoff retries for transient errors (429, 5xx).

- **`prompt_builder.py` (Prompt Engineering & Memory)**
  - **Function:** Dynamically constructs system and user prompts.
  - **Key Logic:** Injects long-term memories from mem0 (`_build_memory_context`), handles conversation summarization (`_compact_history`), and performs intent-based directive injection.
  - **Optimization:** Syncs basic facts and system information directly into the system prompt.

- **`tool_dispatcher.py` (Execution Engine)**
  - **Function:** Dispatches tool calls to registered functions.
  - **Key Logic:** Uses `TOOL_REGISTRY` for execution. Handles contextual argument injection (e.g., `user_id`, `session`) and ensures history validity through `sanitize_history` (essential for local API proxies).

### Execution Flow (Agent Turn)

1. **Initialization:** `run_agent_turn` syncs memories and system context into the system prompt via `prompt_builder`.
2. **LLM Call:** The router calls the selected model with a sanitized message history.
3. **Response Handling:**
   - Text responses are streamed to the gateway (e.g., TUI).
   - Tool calls are identified and executed in parallel via `execute_tool_direct`.
4. **Tool Execution:** Tool results are appended to the history.
5. **Iteration:** The loop repeats until no further tool calls are requested.
6. **Finalization:** Performs post-turn updates (e.g., memory storage, self-upgrade checks).

---

## 2. Gateway Integration (The Senses)

Project Yolo uses a functional integration pattern rather than class inheritance for its gateways. All interfaces follow a consistent contract to interact with the core.

### Gateway Contract

All gateways (TUI, Telegram, Discord, Desktop Bridge) interact with the core through a unified flow:
1. **Session Management:** Retrieve or initialize a `Session` via `SessionManager` in `session.py`.
2. **Orchestration Call:** Invoke the asynchronous `run_agent_turn` in `agent.py`.
3. **Signal Handling:** Provide a `signal_handler` callback. The agent emits real-time updates (streaming tokens, tool calls, status changes) using the `TUIMessage` protocol.

### Implementation Details

- **TUI (`tui.py`):** Uses the Textual framework. Connects UI widgets directly to the `signal_handler` to display agent thoughts and tool outputs in real-time.
- **Messaging Bots (`bot.py`, `discord_gateway.py`):** Map platform-specific events (Telegram/Discord messages) to agent turns. `bot.py` also features a `post_init` hook that can launch the Desktop Bridge in shared-session mode.
- **Desktop (Electron):**
  - **Bridge (`desktop/api_bridge.py`):** Exposes the agent core via an HTTP server. Uses Server-Sent Events (SSE) to stream `TUIMessage` packets to the client.
  - **Main Process (`desktop/main.js`):** Manages the lifecycle of the Python bridge and handles Electron IPC between the renderer and the backend.
  - **Shared State:** The Desktop app and Telegram bot can share the same SQLite-backed session if they use the same `user_id`.

---

## 3. Tool & Plugin System (The Capabilities)

Project Yolo features a dynamic tool system that combines built-in capabilities with an extensible plugin architecture.

### Tool Registration (`registry.py`)

The system uses a decentralized registration pattern:
- **`register_tool` Decorator:** Functions across `tools/*.py` are marked with `@register_tool()`.
- **`TOOL_REGISTRY`:** A central dictionary in `tools/registry.py` that maps tool names to their implementation functions.

### Built-in Toolsets

The `tools/` directory contains specialized modules for various domains:
- **`file_ops.py` / `codebase_ops.py`:** Filesystem and code analysis.
- **`browser_ops.py` / `web_ops.py`:** Web automation and scraping.
- **`gui_ops.py`:** Desktop automation (mouse/keyboard).
- **`system_ops.py`:** OS-level commands and process management.
- **`memory_service.py`:** Interaction with long-term memory (mem0).

### Plugin Architecture (`plugin_manager.py`)

Project Yolo can load tools at runtime from an external directory (`~/.yolo/plugins`):
- **Dynamic Loading:** `plugin_manager.py` scans for `.py` files and imports them using `importlib`.
- **Schema & Handlers:** Plugins are expected to define `PLUGIN_SCHEMAS` (OpenAI-compatible JSON) and matching handler functions.
- **Lifecycle:** Plugins are integrated into the main `TOOL_REGISTRY` during agent initialization.

---

## 4. Deep Core & Workers (The Muscles)

Project Yolo leverages background workers for long-running autonomous tasks and integrates high-performance components (planned or externalized).

### Background Workers (`worker.py`)

- **Autonomous Loop:** `run_worker_loop` manages an independent 'Think-Act-Observe' cycle. It creates an isolated `Session` for each task to prevent context pollution.
- **Task Management:** Triggered via `spawn_worker` (in `tools/team_ops.py`), tasks are persisted in the `background_tasks` table of `yolo_v2.db`.
- **Coordination:** Workers communicate results back to the main agent via the shared database and memory service.

### System Monitoring (`monitoring.py`)

- **Health Checks:** `build_health_payload` provides a snapshot of system status.
- **Metrics:** It tracks active background tasks, pending notifications, and scheduled crons by querying SQLite.
- **Log Integration:** Tails `agent_log.txt` to monitor for recent errors or status updates.

### Deep Core (Rust)

- **Artifacts:** A `yolo-core` binary exists in `rust/yolo-core/target/release/`, indicating build artifacts for a high-performance component.
- **Status:** The source code (`.rs` files and `Cargo.toml`) is currently absent from the workspace (possibly a submodule or external repository). No direct calls from the Python core to a Rust library (via PyO3/CFFI) were found in the current implementation, suggesting it may be used as a standalone binary or is still in development.

---

## 5. State, Memory & Persistence (The Knowledge)

Project Yolo maintains a robust state management system that ensures continuity across sessions and enables long-term learning.

### Session Management (`session.py`)

- **`Session` Data Object:** Encapsulates user ID, message history, tool confirmation status, and agent modes (Yolo/Think).
- **`SessionManager`:** Handles session lifecycle, including creation, retrieval, and timeout management. It uses an `asyncio.Lock` per user to ensure concurrency safety.
- **Optimization:** Implements "dirty" flags and signature-based hashing to minimize redundant SQLite writes during high-frequency updates.

### Persistent Storage (`database_ops.py`)

- **SQLite Backend (`yolo_v2.db`):** A local database using WAL (Write-Ahead Logging) mode for safe concurrent access.
- **Schemas:**
  - `sessions`: Stores full conversation history (JSON-encoded), flags, and last-active timestamps.
  - `background_tasks`: Tracks long-running autonomous worker missions and their results.
  - `notifications` / `crons`: Manages asynchronous alerts and scheduled tasks.

### Long-Term Memory (`tools/memory_service.py`)

- **Integration:** Uses the `mem0` library for "personal memory" capabilities.
- **Workflow:** `prompt_builder.py` queries the memory service at the start of each turn to inject relevant context (basic facts, past interactions) into the system prompt.
- **Persistence:** Memories are stored in a vector database (defaulting to Qdrant) managed by `mem0`, which is independent of the SQLite session store.

---
