import asyncio
import json
from typing import Any, Callable, Optional, List, Dict
from colorama import Fore
from session import Session

async def execute_tool_direct(
    func_name: str,
    func_args: Any,
    user_id: int,
    signal_handler: Optional[Callable] = None,
    session: Any = None,
) -> str:
    import agent
    from agent import log_agent, run_agent_turn
    from prompt_builder import get_background_initial_messages, _compact_history
    if isinstance(func_args, str):
        try:
            func_args = json.loads(func_args)
        except Exception:
            return f"Error: Arguments for {func_name} must be a JSON object string or dict. Got: {func_args}"

    if not isinstance(func_args, dict):
        return f"Error: Invalid arguments for {func_name}; expected object."

    log_agent(user_id, "🔧 TOOL", f"{func_name}({func_args})", Fore.YELLOW)
    if signal_handler:
        await signal_handler(
            f"{agent.TUIMessage.TOOL_CALL}:{json.dumps({'name': func_name, 'args': func_args})}"
        )
    async def _run_with_history_sync(tid: str, objective: str, parent_session: Any, orig_handler: Any):
        from tools.database_ops import update_background_task_history
        worker_session = Session(
            user_id=parent_session.user_id,
            task_id=tid,
            message_history=get_background_initial_messages(),
            yolo_mode=True,
        )
        async def wrapped_handler(payload):
            update_background_task_history(tid, worker_session.message_history)
            if orig_handler:
                await orig_handler(payload)
        
        try:
            res = await run_agent_turn(
                objective, 
                worker_session, 
                signal_handler=wrapped_handler, 
                memory_service=None
            )
        finally:
            update_background_task_history(tid, worker_session.message_history)
        return res

    from tools.registry import TOOL_REGISTRY
    from tools.plugin_manager import PLUGIN_HANDLERS
    import inspect

    target = TOOL_REGISTRY.get(func_name) or PLUGIN_HANDLERS.get(func_name)
    if func_name == "compact_conversation":
        target = _compact_history

    if target:
        # Inject standard contextual arguments if the tool signature requires them
        sig = inspect.signature(target)
        if "user_id" in sig.parameters and "user_id" not in func_args:
            func_args["user_id"] = user_id
        if "session" in sig.parameters and "session" not in func_args:
            func_args["session"] = session
        if "router" in sig.parameters and "router" not in func_args:
            global router
            func_args["router"] = router
        if "confirm_func" in sig.parameters and "confirm_func" not in func_args:
            func_args["confirm_func"] = lambda a, t: True
            
        # Special-case injections for complex background task runners
        if func_name == "run_background_mission" and "mission_coro" in sig.parameters:
            func_args["mission_coro"] = lambda tid: _run_with_history_sync(tid, func_args.get("objective", ""), session, signal_handler)
        elif func_name == "dispatch_parallel_agents" and "mission_coro" in sig.parameters:
            func_args["mission_coro"] = lambda obj, tid: _run_with_history_sync(tid, obj, session, signal_handler)

        # Retry transient errors
        _TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)
        _MAX_RETRIES = 2
        res = None
        for _attempt in range(_MAX_RETRIES + 1):
            try:
                # Case 1: Purely async function (async def)
                if inspect.iscoroutinefunction(target):
                    res = await target(**func_args)
                else:
                    # Case 2/3: Sync function or Lambda
                    # We run it in a thread to keep the event loop responsive
                    res = await asyncio.to_thread(lambda: target(**func_args))
                    
                    # Case 4: The function (usually a lambda) returned a coroutine
                    # This happens when the lambda wraps an async function
                    if inspect.iscoroutine(res):
                        # Important: coroutines MUST be awaited on the event loop thread
                        res = await res
                break  # Success
            except _TRANSIENT_ERRORS as retry_err:
                if _attempt < _MAX_RETRIES:
                    backoff = (2**_attempt) * 0.5  # 0.5s, 1s
                    log_agent(
                        user_id,
                        "🔄 RETRY",
                        f"{func_name} attempt {_attempt+1} failed: {retry_err}. Retrying in {backoff}s...",
                        Fore.YELLOW,
                    )
                    await asyncio.sleep(backoff)
                else:
                    res = f"Error after {_MAX_RETRIES + 1} attempts: {retry_err}"
            except Exception as e:
                res = f"Error in {func_name}: {e}"
                break  # Non-transient error — don't retry

        if res is None:
            res = ""
        if not isinstance(res, str):
            res = str(res)

        if signal_handler:
            await signal_handler(
                f"{agent.TUIMessage.TOOL_RESULT}:{json.dumps({'name': func_name, 'result': res})}"
            )

        if signal_handler and isinstance(res, str) and res.startswith("__SEND_FILE__:"):
            sig = await signal_handler(res)
            if sig:
                res = sig
        log_agent(
            user_id,
            "✅ RESULT",
            str(res)[:200] + "..." if len(str(res)) > 200 else str(res),
            Fore.GREEN,
        )
        return res
    return f"Error: {func_name} not found."


def sanitize_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure history strictly complies with LLM tool-call sequence rules."""
    sanitized = []
    i = 0
    while i < len(history):
        msg = history[i]

        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            expected_ids = {tc["id"] for tc in msg["tool_calls"]}
            tool_responses = []

            j = i + 1
            while j < len(history) and history[j].get("role") == "tool":
                tool_responses.append(history[j])
                j += 1

            found_ids = {tm.get("tool_call_id") for tm in tool_responses}

            # The proxy requires exact 1:1 match of tool calls to tool responses
            if expected_ids == found_ids and len(tool_responses) == len(
                msg["tool_calls"]
            ):
                sanitized.append(msg)
                sanitized.extend(tool_responses)
                i = j
            else:
                # Sequence broken. Strip tool_calls to save text, drop orphaned tool responses
                safe_msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                if not safe_msg.get("content"):
                    safe_msg["content"] = (
                        "[Corrupted tool call sequence removed for safety]"
                    )
                sanitized.append(safe_msg)
                i = j
        elif msg.get("role") == "tool":
            i += 1  # Drop stray tool responses
        else:
            sanitized.append(msg)
            i += 1

    return sanitized

