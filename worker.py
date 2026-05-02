import asyncio
import os
from typing import Any
from session import Session

async def run_worker_loop(user_id: int, task_id: str, role: str, objective: str, memory_service: Any) -> None:
    """An isolated loop for a specialized worker agent."""
    from tools.database_ops import add_worker_task, update_worker_status
    import agent
    import tools
    from tool_dispatcher import execute_tool_direct
    
    # Use the global router from agent module
    router = agent.router
    
    # Ensure a record exists in the DB immediately
    try:
        add_worker_task(task_id, user_id, role, objective)
    except Exception:
        pass # If already added by spawn_worker, ignore

    worker_session = Session(user_id=user_id)
    
    system_prompt = (
        f"You are a specialized worker agent taking on the role of: {role}.\n"
        f"Your specific objective is: {objective}\n"
        f"Your Task ID is: {task_id}\n\n"
        "You operate in an isolated context. You have access to all coding and research tools.\n"
        "CRITICAL: When you have finished the objective, you MUST call `report_completion(task_id=..., summary=...)`.\n"
        "CRITICAL: If you are confused, stuck (e.g. failing tests 3+ times), or blocked by architecture, you MUST call `request_help(task_id=..., reason=..., context=...)`.\n"
        "Do NOT ask the user for input. You run autonomously."
    )
    
    worker_session.message_history = [{"role": "system", "content": system_prompt}]
    
    max_turns = int(os.getenv("WORKER_MAX_TURNS", "30"))
    worker_timeout = int(os.getenv("WORKER_TIMEOUT_SECONDS", "1800"))
    turns = 0
    
    try:
        # Prevent zombie workers by adding a global timeout
        async def _run():
            nonlocal turns
            while turns < max_turns:
                turns += 1
                print(f"[{task_id}] Turn {turns}...")
                try:
                    response = await router.chat_completions(
                        messages=worker_session.message_history,
                        tools=tools.TOOLS_SCHEMAS,
                        tool_choice="auto",
                        stream=False
                    )
                    
                    if not getattr(response, "choices", None) or len(response.choices) == 0:
                        print(f"[{task_id}] Warning: Empty choices from LLM, retrying...")
                        await asyncio.sleep(1)
                        continue
                        
                    msg = response.choices[0].message
                    worker_session.message_history.append(msg.model_dump(exclude_none=True))
                    
                    if not getattr(msg, "tool_calls", None):
                        # Worker didn't call a tool. Force it to report or continue.
                        worker_session.message_history.append({
                            "role": "user", 
                            "content": "You did not call a tool. You must either continue working using tools, `report_completion`, or `request_help`."
                        })
                        continue
                        
                    terminate = False
                    for tc in msg.tool_calls:
                        print(f"[{task_id}] Executing {tc.function.name}...")
                        result = await execute_tool_direct(
                            tc.function.name, 
                            tc.function.arguments, 
                            user_id, 
                            signal_handler=None, 
                            session=worker_session
                        )
                        print(f"[{task_id}] Result: {result[:100]}...")
                        
                        worker_session.message_history.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": result
                        })
                        
                        if "__WORKER_TERMINATE__" in result:
                            terminate = True
                    
                    if terminate:
                        break
                        
                except Exception as e:
                    from tools.database_ops import update_worker_status
                    err_msg = str(e)
                    if "401" in err_msg or "unauthorized" in err_msg.lower():
                        update_worker_status(task_id, "failed", "Unauthorized: LLM token expired or invalid.")
                    else:
                        update_worker_status(task_id, "failed", f"Worker crashed: {e}")
                    return True # Error handled

            if turns >= max_turns:
                from tools.database_ops import update_worker_status
                update_worker_status(task_id, "failed", "Worker hit max turns limit.")
            return False

        await asyncio.wait_for(_run(), timeout=worker_timeout)
    except asyncio.TimeoutError:
        from tools.database_ops import update_worker_status
        update_worker_status(task_id, "failed", f"Worker timed out after {worker_timeout} seconds.")
    except Exception as e:
        from tools.database_ops import update_worker_status
        update_worker_status(task_id, "failed", f"Global worker loop error: {e}")

