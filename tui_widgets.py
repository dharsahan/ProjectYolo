import os
from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static, Markdown, Input, LoadingIndicator
from tools.base import format_log_line

class ChatMessage(Static):
    """A single chat message widget."""
    def __init__(self, role: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self._content = content

    def compose(self) -> ComposeResult:
        role_class = f"role-{self.role.lower()}"
        yield Static(self.role.upper(), classes=f"message-role {role_class}")
        yield Markdown(self._content, classes=f"message-content {role_class}")

class ChatWidget(Vertical):
    """A widget to display a list of chat messages."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_assistant_msg = None
        self.loading_indicator = None

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="message-list"):
            yield Vertical(id="message-container")

    def show_loading(self):
        if not self.loading_indicator:
            container = self.query_one("#message-container", Vertical)
            self.loading_indicator = LoadingIndicator()
            container.mount(self.loading_indicator)
            self.loading_indicator.scroll_visible()

    def hide_loading(self):
        if self.loading_indicator:
            self.loading_indicator.remove()
            self.loading_indicator = None

    def append_message(self, role: str, content: str):
        self.hide_loading()
        container = self.query_one("#message-container", Vertical)
        new_msg = ChatMessage(role=role, content=content)
        container.mount(new_msg)
        new_msg.scroll_visible()
        if role == "assistant":
            self.last_assistant_msg = new_msg
        else:
            self.last_assistant_msg = None

    async def update_live_message(self, content: str):
        self.hide_loading()
        if self.last_assistant_msg is not None:
            # Markdown update might be awaitable in newer Textual versions
            update_task = self.last_assistant_msg.query_one(Markdown).update(content)
            import inspect
            import asyncio
            if inspect.isawaitable(update_task):
                await update_task
            self.last_assistant_msg.scroll_visible()
            # Force UI to process events and render immediately
            await asyncio.sleep(0)
        else:
            self.append_message("assistant", content)
            import asyncio
            await asyncio.sleep(0)

    def end_live_message(self):
        self.hide_loading()
        self.last_assistant_msg = None

class UserInput(Input):

    """A custom input widget for user prompts."""
    pass

class WorkWidget(Vertical):
    """A widget to display agent activity and system health."""
    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="work-scroll"):
            yield Static("No tool running", id="current-tool", classes="work-subpanel")
            yield Static("Background Tasks", id="background-tasks", classes="work-subpanel")
            yield Static("System Health", id="system-health", classes="work-subpanel")

    def update_tool(self, tool_name: str, args: dict):
        tool_panel = self.query_one("#current-tool", Static)
        tool_panel.update(f"[b]Current Tool:[/b] {tool_name}\n[i]{args}[/i]")

    def update_background_tasks(self, tasks: list):
        tasks_panel = self.query_one("#background-tasks", Static)
        if not tasks:
            tasks_panel.update("[b]Background Tasks:[/b]\nNone")
            return
        
        content = "[b]Background Tasks:[/b]\n"
        for task_id, objective, status, created_at in tasks:
            content += f"- {task_id[:8]}: {objective[:30]}... ({status})\n"
        tasks_panel.update(content)

    def update_health(self, health: dict):
        health_panel = self.query_one("#system-health", Static)
        content = "[b]System Health:[/b]\n"
        content += f"LLM: {health.get('llm_provider')} ({health.get('model_name')})\n"
        content += f"Tokens Used: {health.get('total_tokens', 0)}\n"
        content += f"Active Tasks: {health.get('running_background_tasks')}\n"
        content += f"Active Crons: {health.get('active_crons')}\n"
        if health.get('db_error'):
            content += f"DB Error: {health.get('db_error')}\n"
        health_panel.update(content)

class LogWidget(Vertical):
    """A widget to display logs from agent_log.txt."""
    def compose(self) -> ComposeResult:
        yield Static("Log Activity", id="log-title")
        yield ScrollableContainer(Static("", id="log-content"), id="log-scroll")

    def update_logs(self, log_path: str):
        content_panel = self.query_one("#log-content", Static)
        try:
            if not os.path.exists(log_path):
                content_panel.update("Log file not found.")
                return
            
            with open(log_path, "r") as f:
                # Read last 50 lines for better context
                lines = f.readlines()
                last_lines = [format_log_line(line.strip()) for line in lines[-50:]]
                content_panel.update("\n".join(last_lines))
                # Auto-scroll to bottom
                self.query_one("#log-scroll").scroll_end(animate=False)
        except Exception as e:
            content_panel.update(f"Error reading logs: {e}")

