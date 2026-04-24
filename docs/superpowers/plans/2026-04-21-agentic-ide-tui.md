# Agentic IDE TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform YOLO's CLI into a feature-rich split-screen TUI using Textual.

**Architecture:** A Reactive IDE pattern where `agent.py` acts as a logic engine emitting events via an async bridge to a separate Textual UI process.

**Tech Stack:** `Textual`, `Rich`, `asyncio`.

---

### Task 1: Environment & Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add textual to requirements**
```bash
echo "textual>=0.86.2" >> requirements.txt
```

- [ ] **Step 2: Install dependencies**
```bash
source .venv/bin/activate && pip install -r requirements.txt
```

- [ ] **Step 3: Commit**
```bash
git add requirements.txt
git commit -m "chore: add textual dependency"
```

---

### Task 2: Reactive Signal Bridge

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Define TUIMessage types**
```python
# At the top of agent.py
class TUIMessage:
    STREAM = "__STREAM__"
    STATUS = "__STATUS__"
    TOOL_CALL = "__TOOL_CALL__"
    TOOL_RESULT = "__TOOL_RESULT__"
    DONE = "__DONE__"
```

- [ ] **Step 2: Update execute_tool_direct to emit tool events**
Modify the loop in `execute_tool_direct` to send `TOOL_CALL` and `TOOL_RESULT` signals if a `signal_handler` is provided.

- [ ] **Step 3: Commit**
```bash
git add agent.py
git commit -m "feat: enhance SignalHandler with structured TUI messages"
```

---

### Task 3: TUI Skeleton & Layout

**Files:**
- Create: `tui.py`
- Create: `tui.tcss`

- [ ] **Step 1: Implement base TUI app**
```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container, Horizontal, Vertical

class YoloTUI(App):
    CSS_PATH = "tui.tcss"
    BINDINGS = [("q", "quit", "Quit"), ("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Vertical(Static("Chat Panel", id="chat-panel"), classes="column"),
            Vertical(Static("Work Panel", id="work-panel"), classes="column"),
        )
        yield Footer()

if __name__ == "__main__":
    app = YoloTUI()
    app.run()
```

- [ ] **Step 2: Create base CSS**
```css
.column {
    width: 50%;
    border: solid $accent;
    height: 100%;
}
#chat-panel { background: $surface; }
#work-panel { background: $panel; }
```

- [ ] **Step 3: Verify startup**
```bash
python3 tui.py
```

- [ ] **Step 4: Commit**
```bash
git add tui.py tui.tcss
git commit -m "feat: implement base TUI layout skeleton"
```

---

### Task 4: Chat & Input Widgets

**Files:**
- Create: `tui_widgets.py`
- Modify: `tui.py`

- [ ] **Step 1: Implement ChatWidget with Markdown support**
Use `textual.widgets.Markdown` for the message history and a custom `Input` for prompts.

- [ ] **Step 2: Implement Agent Integration**
Use `app.run_worker` to execute `agent.run_agent_turn` in the background without blocking the UI thread.

- [ ] **Step 3: Commit**
```bash
git add tui_widgets.py tui.py
git commit -m "feat: add interactive chat and input widgets"
```

---

### Task 5: Operations & Health Panel

**Files:**
- Modify: `tui_widgets.py`
- Modify: `tui.py`

- [ ] **Step 1: Create WorkWidget**
Add panels for "Current Tool", "Active Tasks" (querying `yolo_v2.db`), and "System Health" (using `monitoring.py`).

- [ ] **Step 2: Implement reactive updates**
Set up a periodic timer in the TUI app to refresh the Health and Tasks panels.

- [ ] **Step 3: Commit**
```bash
git add tui_widgets.py tui.py
git commit -m "feat: implement operations dashboard panel"
```

---

### Task 6: Interactive Confirmations

**Files:**
- Modify: `tui.py`
- Modify: `agent.py`

- [ ] **Step 1: Implement Confirmation Modal**
Create a `ModalScreen` in Textual that pops up when `PendingConfirmationError` is caught.

- [ ] **Step 2: Connect Agent HITL to Modal**
Ensure the agent worker waits for the Modal result before continuing.

- [ ] **Step 3: Commit**
```bash
git add tui.py agent.py
git commit -m "feat: add interactive TUI tool confirmations"
```

---

### Task 7: Final Polish & Entry Point

**Files:**
- Modify: `agent.py`
- Modify: `cli.py`

- [ ] **Step 1: Update main to prefer TUI**
Add a `--tui` flag to `cli.py` (defaulting to True if in an interactive terminal).

- [ ] **Step 2: Add logging to TUI**
Redirect agent logs to a dedicated debug console in the TUI (optional/extra).

- [ ] **Step 3: Final validation**
Run the TUI and execute a multi-step task (e.g., "build a landing page") to verify all panels update correctly.

- [ ] **Step 4: Commit**
```bash
git add agent.py cli.py
git commit -m "feat: finalize TUI integration as primary interface"
```
