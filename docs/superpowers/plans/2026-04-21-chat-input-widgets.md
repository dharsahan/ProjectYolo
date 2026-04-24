# Chat & Input Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement interactive chat functionality in the TUI with markdown rendering and background processing.

**Architecture:** Update TUI with `ChatWidget` and `UserInput`, using Textual's worker system to run the agent in the background and stream updates via signals.

**Tech Stack:** Python, Textual, Markdown.

---

### Task 1: Create `tui_widgets.py`

**Files:**
- Create: `tui_widgets.py`

- [ ] **Step 1: Implement `ChatMessage`, `ChatWidget`, and `UserInput`**

```python
from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static, Markdown, Input
from textual.message import Message

class ChatMessage(Static):
    """A single chat message widget."""
    def __init__(self, role: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.content = content

    def compose(self) -> ComposeResult:
        yield Static(f"[{self.role}]", classes="message-role")
        yield Markdown(self.content, classes="message-content")

class ChatWidget(Vertical):
    """A widget to display a list of chat messages."""
    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="message-list"):
            yield Vertical(id="message-container")

    def append_message(self, role: str, content: str):
        container = self.query_one("#message-container", Vertical)
        new_msg = ChatMessage(role=role, content=content)
        container.mount(new_msg)
        new_msg.scroll_visible()

    def update_live_message(self, content: str):
        container = self.query_one("#message-container", Vertical)
        messages = container.query(ChatMessage)
        if messages:
            last_msg = messages.last()
            if last_msg.role == "assistant":
                last_msg.query_one(Markdown).update(content)
                last_msg.scroll_visible()
                return
        
        # If no assistant message to update, create one
        self.append_message("assistant", content)

class UserInput(Input):
    """A custom input widget for user prompts."""
    pass
```

- [ ] **Step 2: Commit**

```bash
git add tui_widgets.py
git commit -m "feat: add ChatWidget and UserInput widgets"
```

---

### Task 2: Update `tui.tcss`

**Files:**
- Modify: `tui.tcss`

- [ ] **Step 1: Add styles for new widgets**

```css
/* ... existing styles ... */

.message-role {
    text-style: bold;
    color: #3498db;
    margin-top: 1;
}

.message-content {
    background: #2d2d2d;
    padding: 1;
    border-left: solid #3498db;
}

#message-list {
    height: 1fr;
}

#message-container {
    height: auto;
}

UserInput {
    dock: bottom;
    margin-top: 1;
}
```

- [ ] **Step 2: Commit**

```bash
git add tui.tcss
git commit -m "style: add styles for chat widgets"
```

---

### Task 3: Update `tui.py` to use new widgets and run agent

**Files:**
- Modify: `tui.py`

- [ ] **Step 1: Update imports and `ChatPanel`**

```python
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static
from tui_widgets import ChatWidget, UserInput
import agent
from session import Session
import asyncio
import json

class ChatPanel(Static):
    """The panel for chat interaction."""
    def compose(self) -> ComposeResult:
        yield Static("Chat Panel", id="chat-title")
        yield ChatWidget(id="chat-widget")
        yield UserInput(placeholder="Ask me anything...", id="user-input")
```

- [ ] **Step 2: Implement `AgenticIDE` logic**

```python
class AgenticIDE(App):
    CSS_PATH = "tui.tcss"
    BINDINGS = [("q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.session = Session(user_id=1, message_history=[], yolo_mode=True)

    async def on_input_submitted(self, event: UserInput.Submitted) -> None:
        prompt = event.value
        if not prompt:
            return
        
        event.input.value = ""
        chat_widget = self.query_one(ChatWidget)
        chat_widget.append_message("user", prompt)
        
        # Run agent in background
        self.run_worker(self.run_agent(prompt))

    async def run_agent(self, prompt: str) -> None:
        chat_widget = self.query_one(ChatWidget)
        
        async def signal_handler(msg: str):
            if msg.startswith(agent.TUIMessage.STREAM + ":"):
                content = msg[len(agent.TUIMessage.STREAM) + 1:]
                self.call_from_thread(chat_widget.update_live_message, content)
            elif msg.startswith(agent.TUIMessage.STATUS + ":"):
                status = msg[len(agent.TUIMessage.STATUS) + 1:]
                # Update status in TUI if needed
                pass

        await agent.run_agent_turn(
            prompt, 
            self.session, 
            signal_handler=signal_handler
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield ChatPanel(id="chat-panel")
            yield WorkPanel(id="work-panel")
        yield Footer()
```

- [ ] **Step 3: Commit**

```bash
git add tui.py
git commit -m "feat: connect chat widgets and run agent in background"
```

---

### Task 4: Verification

- [ ] **Step 1: Run the TUI and test interaction**

Run: `python tui.py`
Expected: TUI opens, can type in the input field, agent responds and streams markdown content.

- [ ] **Step 2: Final Commit**

```bash
git commit --allow-empty -m "feat: add interactive chat and input widgets"
```
