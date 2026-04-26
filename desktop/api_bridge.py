#!/usr/bin/env python3
"""Lightweight HTTP API bridge for the Yolo Desktop app.

This bridge is a thin gateway — just like bot.py (Telegram) or discord_gateway.py.
It reuses the SAME SessionManager → SQLite → Mem0 stack, so Desktop and Telegram
share conversation history, mode flags, pending confirmations, and long-term memory.

Architecture:
  Telegram  ─┐
  Discord   ─┤── SessionManager ── SQLite (~/.yolo/yolo_v2.db)
  CLI       ─┤                  └─ Mem0/Qdrant (long-term memory)
  Desktop   ─┘
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure the project root is on the path so we can import agent/session/tools.
# When imported from server.py, the CWD is already correct.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from aiohttp import web

import agent as yolo_agent
from session import SessionManager

# ── Shared state (same as bot.py) ──
TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
session_manager: SessionManager = None  # type: ignore

# Use the same user ID as Telegram so sessions/memories are shared.
_allowed = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
DEFAULT_USER_ID = int(_allowed.split(",")[0].strip()) if _allowed.strip() else 1


# ── HTTP Handlers ──

async def handle_chat(request: web.Request) -> web.Response:
    """POST /chat  — send a user message through the shared session."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    message = data.get("message", "").strip()
    user_id = int(data.get("user_id", 1))

    if not message:
        return web.json_response({"error": "Empty message"}, status=400)

    # Use the SAME session that Telegram/CLI would use for this user_id.
    # SessionManager.get_or_create() loads from SQLite if not in memory.
    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)

        try:
            response = await yolo_agent.run_agent_turn(
                message,
                session,
                signal_handler=None,
                memory_service=session_manager.memory,
            )
            session_manager.save(user_id)
            return web.json_response({"response": response})
        except yolo_agent.PendingConfirmationError as e:
            # Desktop defaults to YOLO — auto-approve and execute.
            result = await yolo_agent.execute_tool_direct(
                e.action, e.tool_args, user_id, signal_handler=None, session=session
            )
            # Patch the HITL placeholder in history with real result
            for msg in reversed(session.message_history):
                if msg.get("role") == "tool" and msg.get("tool_call_id") == e.tool_call_id:
                    msg["content"] = result
                    break
            session.history_dirty = True

            # Re-run the turn to get the final text response
            try:
                response = await yolo_agent.run_agent_turn(
                    None, session, signal_handler=None, memory_service=session_manager.memory
                )
            except Exception:
                response = f"Tool executed: {result}"

            session_manager.save(user_id)
            return web.json_response({"response": response})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)


async def handle_command(request: web.Request) -> web.Response:
    """POST /command  — execute a slash command against the shared session."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    cmd = data.get("command", "").strip().lower()
    args = data.get("args", [])
    user_id = int(data.get("user_id", 1))

    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        result = ""

        try:
            if cmd == "start":
                session_manager.clear(user_id)
                result = "Session reset. Welcome to Yolo!"

            elif cmd == "status":
                history_len = len(session.message_history)
                compact_threshold = yolo_agent.AUTO_COMPACT_THRESHOLD
                pending = len(session.pending_confirmations)
                mode = "⚡ YOLO (Full Access)" if session.yolo_mode else "🛡️ Safe (HITL)"
                think = "🧠 ON" if getattr(session, "think_mode", False) else "⚙️ OFF"
                policy = getattr(session, "think_mode_policy", "auto")
                result = (
                    f"**Status Report**\n"
                    f"- Mode: {mode}\n"
                    f"- Think mode: {think}\n"
                    f"- Think policy: `{policy}`\n"
                    f"- History: `{history_len}/{compact_threshold}` messages\n"
                    f"- Pending confirmations: **{pending}**\n"
                    f"- LLM calls: `{getattr(session, 'llm_call_count', 0)}`\n"
                    f"- Tokens: `{getattr(session, 'total_tokens', 0)}` "
                    f"(prompt: `{getattr(session, 'total_prompt_tokens', 0)}` "
                    f"+ completion: `{getattr(session, 'total_completion_tokens', 0)}`)\n"
                    f"- Model: `{yolo_agent.router.config.model}`\n"
                    f"- Provider: `{yolo_agent.router.config.provider}`"
                )

            elif cmd == "mode":
                if not args:
                    current = "YOLO" if session.yolo_mode else "Safe"
                    result = f"Current mode: **{current}**. Use `/mode yolo` or `/mode safe`."
                elif args[0].lower() == "yolo":
                    session.yolo_mode = True
                    result = "⚡ **YOLO Mode Enabled!** All actions execute without confirmation."
                elif args[0].lower() == "safe":
                    session.yolo_mode = False
                    result = "🛡️ **Safe Mode Enabled.** Destructive actions require confirmation."
                else:
                    result = "Unknown mode. Use `/mode yolo` or `/mode safe`."
                session_manager.save(user_id)

            elif cmd == "think":
                if not args:
                    current = "On" if session.think_mode else "Off"
                    policy = getattr(session, "think_mode_policy", "auto")
                    result = f"Think mode: **{current}**. Policy: **{policy}**."
                elif args[0].lower() in {"on", "true", "enable"}:
                    session.think_mode_policy = "force_on"
                    session.think_mode = True
                    result = "🧠 **Think Mode Enabled.** Policy set to `force_on`."
                elif args[0].lower() in {"off", "false", "disable"}:
                    session.think_mode_policy = "force_off"
                    session.think_mode = False
                    result = "⚙️ **Think Mode Disabled.** Policy set to `force_off`."
                elif args[0].lower() in {"auto", "smart", "default"}:
                    session.think_mode_policy = "auto"
                    session.think_mode = False
                    result = "🤖 **Think Mode Auto** enabled."
                else:
                    result = "Unknown option. Use `/think on`, `/think off`, or `/think auto`."
                session_manager.save(user_id)

            elif cmd == "compact":
                await yolo_agent._compact_history(session, yolo_agent.router)
                session_manager.save(user_id)
                result = f"✅ History compacted. Now {len(session.message_history)} messages."

            elif cmd == "tools":
                import tools
                lines = ["**Available Tools:**\n"]
                for schema in tools.TOOLS_SCHEMAS:
                    name = schema["function"]["name"]
                    desc = schema["function"]["description"]
                    lines.append(f"- `{name}`: {desc}")
                result = "\n".join(lines)

            elif cmd == "experiences":
                from tools.experience_ops import list_experiences
                result = list_experiences(user_id)

            elif cmd == "schedules":
                from tools.cron_ops import get_scheduled_tasks
                result = get_scheduled_tasks(user_id)

            elif cmd == "memories":
                from tools.memory_ops import memory_list
                result = memory_list(user_id)

            elif cmd == "facts":
                if session.message_history and session.message_history[0].get("role") == "system":
                    content = str(session.message_history[0].get("content", ""))
                    facts = yolo_agent.extract_auto_basic_facts(content)
                    if facts:
                        lines = [f"{i+1}. {f}" for i, f in enumerate(facts)]
                        result = "**Auto Basic Facts:**\n\n" + "\n".join(lines)
                    else:
                        result = "No auto basic facts currently injected."
                else:
                    result = "No system prompt found for this session."

            elif cmd == "forget":
                from tools.memory_ops import memory_wipe
                result = memory_wipe(user_id)

            elif cmd == "cancel":
                if session.pending_confirmations:
                    for p in session.pending_confirmations:
                        session.message_history.append({
                            "role": "tool",
                            "tool_call_id": p["tool_call_id"],
                            "name": p["action"],
                            "content": "Action denied by user.",
                        })
                    count = len(session.pending_confirmations)
                    session.pending_confirmations = []
                    session.history_dirty = True
                    session_manager.save(user_id)
                    result = f"✅ {count} pending action(s) cancelled."
                else:
                    result = "No pending actions."

            else:
                result = (
                    f"Unknown command: `/{cmd}`. Available: "
                    "`/start`, `/status`, `/mode`, `/think`, `/compact`, `/tools`, "
                    "`/experiences`, `/schedules`, `/memories`, `/facts`, `/forget`, `/cancel`."
                )

        except Exception as exc:
            result = f"Error executing /{cmd}: {exc}"

    return web.json_response({"response": result, "command": cmd})


async def handle_health(request: web.Request) -> web.Response:
    """GET /health"""
    return web.json_response({
        "status": "ok",
        "model": yolo_agent.router.config.model,
        "provider": yolo_agent.router.config.provider,
        "default_user_id": DEFAULT_USER_ID,
    })


async def handle_session_info(request: web.Request) -> web.Response:
    """GET /session?user_id=N  — return current session state for the UI."""
    user_id = int(request.query.get("user_id", "1"))
    session = session_manager.get_or_create(user_id)

    # Extract message history (excluding system prompt) for the UI
    messages = []
    for msg in session.message_history:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role in ("user", "assistant"):
            content = msg.get("content", "")
            if content and not content.startswith("[CONVERSATION_SUMMARY]"):
                messages.append({"role": role, "content": content})

    return web.json_response({
        "user_id": user_id,
        "yolo_mode": session.yolo_mode,
        "think_mode": getattr(session, "think_mode", False),
        "think_mode_policy": getattr(session, "think_mode_policy", "auto"),
        "history_length": len(session.message_history),
        "pending_confirmations": len(session.pending_confirmations),
        "messages": messages,
        "llm_call_count": getattr(session, "llm_call_count", 0),
        "total_tokens": getattr(session, "total_tokens", 0),
    })


# ── App setup ──

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/chat", handle_chat)
    app.router.add_post("/command", handle_command)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/session", handle_session_info)
    return app


def init_session_manager(shared_manager: SessionManager = None):
    """Set the module-level session_manager. Accepts an external one for
    shared-gateway mode (when started from server.py alongside Telegram)."""
    global session_manager
    if shared_manager is not None:
        session_manager = shared_manager
    elif session_manager is None:
        session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)
    return session_manager


async def run_desktop_bridge(
    host: str = "127.0.0.1",
    port: int = 0,
    shared_session_manager: SessionManager = None,
) -> None:
    """Start the desktop bridge as an async task (called from server.py).

    This runs forever alongside Telegram/Discord gateways.
    """
    if port == 0:
        port = int(os.getenv("DESKTOP_BRIDGE_PORT", "8790"))

    init_session_manager(shared_session_manager)
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    print(f"[desktop-bridge] Listening on http://{host}:{port}")
    print(f"[desktop-bridge] Session shared with Telegram/CLI/Discord")
    sys.stdout.flush()

    # Run forever (until cancelled)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()
        raise


def main():
    """Standalone entry point (for development / testing)."""
    init_session_manager()
    port = int(os.getenv("DESKTOP_BRIDGE_PORT", "8790"))
    app = create_app()

    print(f"[desktop-bridge] Starting on http://127.0.0.1:{port}")
    print(f"[desktop-bridge] Model: {yolo_agent.router.config.model} via {yolo_agent.router.config.provider}")
    print(f"[desktop-bridge] Session DB: ~/.yolo/yolo_v2.db (shared with Telegram/CLI)")
    print("[desktop-bridge] Bridge ready")
    sys.stdout.flush()

    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()

