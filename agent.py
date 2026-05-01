import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from colorama import Fore, Style, init
from dotenv import load_dotenv

import tools
from llm_router import LLMRouter, load_llm_config
from session import Session
from worker import run_worker_loop
from tool_dispatcher import execute_tool_direct, sanitize_history

from prompt_builder import *

class TUIMessage:
    STREAM = "__STREAM__"
    STATUS = "__STATUS__"
    TOOL_CALL = "__TOOL_CALL__"
    TOOL_RESULT = "__TOOL_RESULT__"
    DONE = "__DONE__"

init(autoreset=True)
load_dotenv()

VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

def _get_router() -> LLMRouter:
    """Helper to load configuration and return a router instance."""
    config = load_llm_config()
    if not config.model:
        raise ValueError("No LLM model configured.")
    return LLMRouter(config)

router = _get_router()

def reload_router():
    """Manually reload the global router (useful for tests or env changes)."""
    global router
    router = _get_router()
AUTO_COMPACT_THRESHOLD = int(os.getenv("AUTO_COMPACT_THRESHOLD", "40"))
PROMPTS_DIR = Path(__file__).resolve().parent / "configs" / "prompts"

async def run_agent_turn(
    user_msg: Optional[str],
    session: Session,
    signal_handler: Optional[Callable] = None,
    memory_service: Any = None,
) -> str:
    self_upgrade_active = False
    self_upgrade_start_index = len(session.message_history)
    experience_update_active = False
    experience_update_start_index = len(session.message_history)

    if not session.message_history:
        session.message_history = get_initial_messages()

    _normalize_single_system_message(session)

    # Performance: fetch get_all once per turn, share between the two consumers.
    _turn_all_memories = (
        _fetch_all_memories(memory_service, session.user_id) if memory_service else []
    )

    # Keep durable, compact facts in base system prompt.
    _sync_basic_facts_into_system_prompt(
        session, memory_service, all_results=_turn_all_memories
    )

    # Auto-think behavior: auto policy enables think mode for complex prompts;
    # explicit on/off is controlled by think_mode_policy.
    if getattr(session, "think_mode_policy", "auto") == "auto" and user_msg is not None:
        session.think_mode = _is_complex_task_prompt(user_msg)

    if getattr(session, "think_mode", False):
        _inject_system_directive(session, THINK_MODE_SYSTEM_DIRECTIVE)

    if user_msg:
        memory_context = _build_memory_context(
            memory_service, session.user_id, user_msg, all_results=_turn_all_memories
        )
        _merge_memory_context_into_system_prompt(session, memory_context)

        if _is_self_upgrade_request(user_msg):
            self_upgrade_active = True
            _inject_system_directive(session, SELF_UPGRADE_SYSTEM_DIRECTIVE)
            self_upgrade_start_index = len(session.message_history)

        if _is_experience_update_request(user_msg):
            experience_update_active = True
            _inject_system_directive(session, EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE)
            experience_update_start_index = len(session.message_history)

        session.message_history.append({"role": "user", "content": user_msg})
        session.history_dirty = True
        log_agent(session.user_id, "IN", user_msg, Fore.CYAN)

        # Inject GUI perception directive when GUI interaction is detected
        if _is_gui_interaction_request(user_msg):
            _inject_system_directive(session, GUI_PERCEPTION_DIRECTIVE)

    _normalize_single_system_message(session)

    while True:
        assistant_msg = None
        for msg in reversed(session.message_history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                assistant_msg = msg
                break

        if assistant_msg:
            answered = {
                m["tool_call_id"]
                for m in session.message_history
                if m.get("role") == "tool"
            }
            unanswered = [
                tc for tc in assistant_msg["tool_calls"] if tc["id"] not in answered
            ]

            if unanswered:
                log_agent(
                    session.user_id,
                    "RESUME",
                    f"Completing turn with {len(unanswered)} tool calls...",
                    Fore.YELLOW,
                )

                if signal_handler:
                    tool_names_str = ", ".join(
                        set(tc["function"]["name"] for tc in unanswered)
                    )
                    await signal_handler(
                        f"__STATUS__: Executing tools: {tool_names_str}"
                    )

                # Prepare tasks for parallel execution
                tasks = []
                # Clear previous pending list if we're starting a fresh turn
                # (but technically they should have been resolved already)
                session.pending_confirmations = []

                for tool_call in unanswered:
                    func_name = tool_call["function"]["name"]
                    tc_id = tool_call["id"]
                    try:
                        args = json.loads(tool_call["function"].get("arguments", "{}"), strict=False)
                    except Exception:
                        args = {}

                    if "_invalid_json" in args:
                        res = f"Error: Your tool call arguments were not valid JSON. Exception: {args.get('_error')}\nYou sent: {args.get('_invalid_json')}\nPlease fix your JSON syntax (e.g. properly escape newlines as \\n and quotes) and try again."
                        session.message_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "name": func_name,
                                "content": res,
                            }
                        )
                        session.history_dirty = True
                        continue

                    if not isinstance(args, dict):
                        args = {}

                    # Check for nested background missions
                    if func_name == "run_background_mission":
                        system_prompt = ""
                        if (
                            session.message_history
                            and session.message_history[0].get("role") == "system"
                        ):
                            system_prompt = session.message_history[0].get(
                                "content", ""
                            )
                        if "detached background mission" in system_prompt.lower():
                            res = "Skipping nested `run_background_mission` call: already running in background mode."
                            session.message_history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "name": func_name,
                                    "content": res,
                                }
                            )
                            session.history_dirty = True
                            continue

                    # HITL Check
                    out_of_scope = _is_out_of_scope(args)
                    if (
                        _is_destructive_or_sensitive_tool(func_name) or out_of_scope
                    ) and not session.yolo_mode:
                        pending_path = _extract_tool_path(args)
                        # PROXY COMPLIANCE: Answer the call with a placeholder so the turn is technically "complete"
                        session.message_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "name": func_name,
                                "content": "[HITL_PENDING]",
                            }
                        )
                        session.history_dirty = True
                        session.pending_confirmations.append(
                            {
                                "action": func_name,
                                "path": pending_path,
                                "args": args,
                                "tool_call_id": tc_id,
                            }
                        )
                        continue

                    # Define the task to be executed
                    async def run_and_store(
                        name=func_name, arguments=args, call_id=tc_id
                    ):
                        result = await execute_tool_direct(
                            name,
                            arguments,
                            session.user_id,
                            signal_handler,
                            session=session,
                        )
                        return {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": result,
                        }

                    tasks.append(run_and_store())

                if tasks:
                    # Execute all non-HITL tasks in parallel
                    results = await asyncio.gather(*tasks)
                    session.message_history.extend(results)
                    session.history_dirty = True

                if session.pending_confirmations:
                    if signal_handler:
                        await signal_handler("__STATUS__: ")  # Clear status
                    # Just raise the first one for backwards compat with PendingConfirmationError
                    # but the session now contains ALL of them.
                    first = session.pending_confirmations[0]
                    raise PendingConfirmationError(
                        first["action"],
                        first["path"],
                        first["tool_call_id"],
                        first["args"],
                    )

                continue

        _normalize_single_system_message(session)

        # Auto-compact history if it exceeds threshold
        if len(session.message_history) > AUTO_COMPACT_THRESHOLD:
            await _compact_history(session, router)

        log_agent(session.user_id, "THINKING", "Consulting LLM...", Fore.MAGENTA)
        if signal_handler:
            await signal_handler("__STATUS__: Consulting AI model...")

        # Performance: only sanitize when the history has actually been mutated
        # since the last sanitize. The check is cheap and skipping the O(n)
        # rebuild on every LLM round (especially during multi-step tool loops)
        # noticeably reduces per-turn overhead for long conversations.
        if getattr(session, "history_dirty", True):
            session.message_history = sanitize_history(session.message_history)
            session.history_dirty = False

        try:
            response = await router.chat_completions(
                messages=session.message_history,
                tools=tools.TOOLS_SCHEMAS,
                tool_choice="auto",
                stream=True,
            )
        except Exception as e:
            return f"Error: LLM issue: {e}"

        last_stream_time = 0.0
        full_content = ""
        tool_calls_acc: list = []
        usage = None
        has_choices = False

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage

            if not getattr(chunk, "choices", None):
                continue

            has_choices = True
            delta = chunk.choices[0].delta

            if getattr(delta, "content", None):
                full_content += delta.content
                now = time.time()
                if now - last_stream_time > 0.1 and signal_handler:
                    await signal_handler(f"__STREAM__:{full_content}")
                    last_stream_time = now

            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = getattr(tc, "index", None)
                    if idx is None:
                        idx = 0
                    while len(tool_calls_acc) <= idx:
                        tool_calls_acc.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        )

                    tc_dict = tc.model_dump(exclude_none=True)

                    def _deep_merge(target, source):
                        for k, v in source.items():
                            if k == "index":
                                continue
                            if isinstance(v, dict):
                                if k not in target or not isinstance(target[k], dict):
                                    target[k] = {}
                                _deep_merge(target[k], v)
                            elif (
                                isinstance(v, str)
                                and k in target
                                and isinstance(target[k], str)
                            ):
                                if k in ["name", "arguments", "id"]:
                                    target[k] += v
                                else:
                                    target[k] = v
                            else:
                                target[k] = v

                    _deep_merge(tool_calls_acc[idx], tc_dict)

        if not has_choices and not usage:
            return "Error: No AI response."

        # Final flush of the stream if there was any content
        if full_content and signal_handler:
            await signal_handler(f"__STREAM__:{full_content}")
            await signal_handler("__STREAM_END__:")

        # ── Token / cost tracking ──
        if usage:
            session.total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            session.total_completion_tokens += (
                getattr(usage, "completion_tokens", 0) or 0
            )
            session.total_tokens += getattr(usage, "total_tokens", 0) or 0
        session.llm_call_count += 1

        msg_dict: dict[str, Any] = {"role": "assistant", "content": full_content}
        if tool_calls_acc:
            # Robustness: Filter out tool calls that lack a function name.
            # Also ensure 'arguments' is a valid JSON string (at least "{}")
            # to satisfy strict validation in some OpenAI-compatible proxies (e.g. Ollama).
            valid_tool_calls = []
            for tc in tool_calls_acc:
                if tc.get("function", {}).get("name"):
                    # Ensure arguments is a string (some proxies might return a dict)
                    args = tc["function"].get("arguments")
                    if isinstance(args, dict):
                        tc["function"]["arguments"] = json.dumps(args)
                    elif not args or not isinstance(args, str):
                        tc["function"]["arguments"] = "{}"
                    else:
                        # Optional: attempt to validate JSON to avoid 400s on broken strings
                        try:
                            json.loads(tc["function"]["arguments"], strict=False)
                        except Exception as e:
                            # If it's not valid JSON, we wrap it in a valid JSON object so we don't get a 400 error
                            # from the provider on the next turn, while preserving the bad input so the agent sees the error.
                            tc["function"]["arguments"] = json.dumps({"_invalid_json": tc["function"]["arguments"], "_error": str(e)})
                    
                    # Ensure 'id' is not empty if the model failed to provide one
                    if not tc.get("id"):
                        tc["id"] = f"call_{int(time.time()*1000)}"
                        
                    valid_tool_calls.append(tc)
            
            if valid_tool_calls:
                msg_dict["tool_calls"] = valid_tool_calls

        session.message_history.append(msg_dict)
        session.history_dirty = True

        if not tool_calls_acc:
            if self_upgrade_active:
                used_tools = _collect_turn_tool_names(
                    session.message_history, self_upgrade_start_index
                )
                run_bash_commands = _collect_run_bash_commands(
                    session.message_history,
                    self_upgrade_start_index,
                )
                missing = _missing_self_upgrade_phases(
                    used_tools,
                    run_bash_commands=run_bash_commands,
                    require_pytest=_repo_has_tests(),
                )
                if missing:
                    guidance = (
                        "Before finishing, you must complete all SELF-UPGRADE phases. "
                        f"Missing phases: {', '.join(missing)}. "
                        "Continue by calling tools to complete missing phases, then finalize. "
                        "If `validation_pytest` is missing, run at least one `pytest` command via `run_bash`."
                    )
                    session.message_history.append(
                        {"role": "user", "content": guidance}
                    )
                    session.history_dirty = True
                    continue

            if experience_update_active:
                used_tools = _collect_turn_tool_names(
                    session.message_history,
                    experience_update_start_index,
                )
                if "learn_experience" not in used_tools:
                    guidance = (
                        "Before finishing, execute `learn_experience` at least once to persist the lesson. "
                        "Then provide confirmation that the experience was actually stored."
                    )
                    session.message_history.append(
                        {"role": "user", "content": guidance}
                    )
                    session.history_dirty = True
                    continue

            if memory_service and user_msg:
                try:
                    memory_service.add(
                        [
                            {"role": "user", "content": user_msg},
                            {"role": "assistant", "content": full_content},
                        ],
                        user_id=str(session.user_id),
                    )
                except Exception as e:
                    from tools.base import audit_log
                    audit_log("auto_memory_add", {"user_id": session.user_id}, "error", str(e))

            if signal_handler:
                await signal_handler("__STATUS__: ")  # Clear status
            return full_content or "Task completed."


def main():
    import cli
    cli.main()


if __name__ == "__main__":
    main()
