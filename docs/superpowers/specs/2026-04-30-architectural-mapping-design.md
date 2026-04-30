# Design Spec: Comprehensive Architectural Mapping of Project Yolo

**Date:** 2026-04-30
**Topic:** Architectural Mapping
**Goal:** Provide a deep, top-down analysis of Project Yolo's architecture, covering core orchestration, gateway integration, tool systems, cross-language interop, and state management.

## 1. Core Orchestration (The Brain)
- **agent.py:** The central orchestrator managing the loop of reasoning, tool calling, and response generation.
- **llm_router.py:** Logic for routing prompts to different LLM providers/models.
- **prompt_builder.py:** Dynamic construction of system and user prompts.
- **tool_dispatcher.py:** Registry and execution engine for all tools.

## 2. Gateway Integration (The Senses)
- **tui.py / tui_widgets.py:** Text-based interface for interactive use.
- **discord_gateway.py / bot.py:** External service bridges.
- **desktop/ (Electron):** Visual/Desktop entry point and its bridge to the Python core.
- **server.py / health_server.py:** API entry points and monitoring.

## 3. Tool & Plugin System (The Capabilities)
- **tools/**: Directory containing specialized tool modules (file_ops, browser_ops, etc.).
- **plugin_manager.py**: Logic for dynamic loading and lifecycle management of tools/plugins.

## 4. Deep Core & Workers (The Muscles)
- **rust/yolo-core/**: High-performance core logic in Rust.
- **worker.py**: Background process management for long-running tasks.
- **monitoring.py**: System health and performance tracking.

## 5. State & Memory (The Knowledge)
- **session.py**: Management of conversation state and context windows.
- **memory_service.py / memory_ops.py**: Long-term memory management using mem0.
- **database_ops.py / yolo_v2.db**: SQLite-based persistence.

## 6. Analysis Methodology
- **Codebase Investigator:** Use the sub-agent to map symbols, dependencies, and call graphs.
- **Manual Review:** Deep dive into key files (`agent.py`, `tool_dispatcher.py`) for logic validation.
- **Visual Companion:** Generate diagrams for each phase to visualize interactions.

## 7. Success Criteria
- A clear understanding of how a user request flows through the entire system.
- Identification of key interfaces and data formats.
- Visual representation of the system architecture.
