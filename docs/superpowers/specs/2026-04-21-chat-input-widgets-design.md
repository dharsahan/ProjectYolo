# TUI Chat & Input Widgets Design

**Goal:** Implement interactive chat functionality in the TUI, allowing users to send prompts and see the agent's response in real-time with markdown formatting.

## Architecture

The TUI will be updated to include a scrollable chat display and an input field. Real-time updates will be handled by a background worker that runs the agent's turn and communicates back to the UI thread via signals.

### Components

1.  **`ChatWidget` (in `tui_widgets.py`):**
    *   A `Vertical` container that holds message blocks.
    *   Uses a `ScrollableContainer` to manage overflow.
    *   `ChatMessage` widget: A simple wrapper around `Markdown` to display individual messages.
    *   `append_message(role: str, content: str)`: Creates and appends a new `ChatMessage`.
    *   `update_live_message(content: str)`: Updates the content of the most recent assistant message (used for streaming).

2.  **`UserInput` (in `tui_widgets.py`):**
    *   Extends Textual's `Input` widget.
    *   Styled for the chat interface.

3.  **`AgenticIDE` App (in `tui.py`):**
    *   Manages the lifecycle of the agent interaction.
    *   Maintains a `Session` object.
    *   `on_input_submitted`:
        *   Triggered when the user presses Enter in the `UserInput` field.
        *   Appends the user's message to the `ChatWidget`.
        *   Runs `agent.run_agent_turn` in a background worker.
    *   `signal_handler(message: str)`:
        *   Processes signals from the agent (streaming, status updates, tool calls).
        *   Uses `app.call_from_thread` to update widgets safely.

## Data Flow

1.  **User Input:** User types prompt -> `Input.Submitted` -> UI Thread.
2.  **Agent Start:** UI Thread -> `app.run_worker(agent.run_agent_turn)` -> Worker Thread.
3.  **Streaming Response:** Agent -> `signal_handler("__STREAM__:...")` -> `app.call_from_thread` -> `ChatWidget.update_live_message`.
4.  **Completion:** Agent returns final content -> Worker finishes -> UI Thread updates (if needed).

## Testing

*   Manual testing of the TUI:
    *   Type a prompt and ensure it appears in the chat.
    *   Verify the agent's response streams in.
    *   Verify markdown rendering (e.g., code blocks).
    *   Verify auto-scrolling to the bottom.

## Success Criteria

*   User can interact with the agent through the TUI.
*   Responses are rendered with markdown.
*   Streaming updates are visible in real-time.
*   Background processing prevents the UI from freezing.
