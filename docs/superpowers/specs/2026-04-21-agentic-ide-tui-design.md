# Spec: YOLO Agentic IDE TUI

**Date:** 2026-04-21  
**Status:** Draft  
**Topic:** TUI Implementation using Textual

## 1. Vision
Transform the current line-by-line YOLO CLI into a high-fidelity "Agentic IDE." The TUI will provide a split-screen experience where the user can chat with the agent while simultaneously observing its active work, background tasks, and system health.

## 2. Core Features
- **Split-Screen Layout:**
    - **Left Panel (Chat):** A scrollable conversation area with high-quality markdown rendering and a persistent input bar at the bottom.
    - **Right Panel (Work):** A multi-tab or collapsible area showing:
        - **Active Work:** Current tool execution, file paths being modified, and research URLs.
        - **Tasks:** A list of background missions (running, completed, failed).
        - **System Health:** LLM model info, token usage, and database status.
- **Streaming UI:** Real-time text streaming for agent responses.
- **Interactive Tool Confirmations:** Tool approvals handled via non-blocking UI overlays or dedicated status bars.
- **Integrated Watchdog:** The "Wait or Not" feature integrated into the TUI flow.

## 3. Architecture (Reactive IDE)
The design follows a **Reactive IDE** pattern using the **Textual** library.

- **`agent.py` (Core):** Remains the source of truth for logic. It will be updated to emit events via a `TUISignalHandler`.
- **`tui.py` (New Entry Point):** The primary Textual `App`. It manages widgets and listens for events from the agent.
- **`SignalHandler` Interface:** A bridge that translates agent actions (e.g., `__STREAM__`, `__STATUS__`, tool calls) into Textual messages.

### Data Flow
1. User types in the TUI input.
2. TUI sends the prompt to the agent worker.
3. Agent executes, calling the `SignalHandler`.
4. `SignalHandler` posts messages to the TUI.
5. TUI reactive widgets update their content based on these messages.

## 4. Technical Stack
- **Library:** `Textual` (CSS-based layout, reactive components).
- **Styling:** JetBrains Mono font (if available), Slate/Sky color palette.
- **Async:** Full `asyncio` integration for non-blocking UI and agent execution.

## 5. Success Criteria
1. The TUI launches and allows full interaction with the YOLO agent.
2. Agent responses stream smoothly in the chat panel.
3. The right panel accurately reflects background task status.
4. The user can background/cancel long-running tools without the UI freezing.

