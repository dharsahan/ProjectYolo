import asyncio
import os
import logging
from typing import Any
from session import Session
import agent

logger = logging.getLogger(__name__)

async def run_worker_loop(user_id: int, task_id: str, role: str, objective: str, memory_service: Any) -> None:
    """An isolated loop for a specialized worker agent using central orchestration."""
    from tools.database_ops import add_worker_task, update_worker_status
    
    # Ensure a record exists in the DB immediately
    try:
        add_worker_task(task_id, user_id, role, objective)
    except Exception:
        pass # If already added by spawn_worker, ignore

    worker_session = Session(user_id=user_id)
    # Default worker to YOLO mode as it runs autonomously
    worker_session.yolo_mode = True
    
    # Specialized system prompt for the worker
    system_prompt = (
        f"You are a specialized worker agent taking on the role of: {role}.\n"
        f"Your specific objective is: {objective}\n"
        f"Your Task ID is: {task_id}\n\n"
        "You operate in an isolated context. You have access to all coding and research tools.\n"
        "CRITICAL: When you have finished the objective, you MUST call `report_completion(task_id=..., summary=...)`.\n"
        "CRITICAL: If you are confused, stuck (e.g. failing tests 3+ times), or blocked by architecture, you MUST call `request_help(task_id=..., reason=..., context=...)`.\n"
        "Do NOT ask the user for input. You run autonomously."
    )
    
    # Initialize history with the specialized prompt
    worker_session.message_history = [{"role": "system", "content": system_prompt}]
    
    max_turns = int(os.getenv("WORKER_MAX_TURNS", "30"))
    worker_timeout = int(os.getenv("WORKER_TIMEOUT_SECONDS", "1800"))
    turns = 0
    
    try:
        async def _run():
            nonlocal turns
            current_prompt = None # Start with None since system prompt is already set
            
            while turns < max_turns:
                turns += 1
                print(f"[{task_id}] Turn {turns}...")
                
                try:
                    result = await agent.run_agent_turn(
                        current_prompt,
                        worker_session,
                        signal_handler=None,
                        memory_service=memory_service
                    )
                    
                    if "__WORKER_TERMINATE__" in result:
                        print(f"[{task_id}] Worker task terminated normally.")
                        break
                        
                    # If the agent didn't terminate, continue with a reminder
                    current_prompt = "Please continue working towards the objective. Use `report_completion` once finished."
                    
                except Exception as e:
                    err_msg = str(e)
                    print(f"[{task_id}] Error in worker turn: {err_msg}")
                    if "401" in err_msg or "unauthorized" in err_msg.lower():
                        update_worker_status(task_id, "failed", "Unauthorized: LLM token expired or invalid.")
                    else:
                        update_worker_status(task_id, "failed", f"Worker crashed during turn: {e}")
                    return True # Handled

            if turns >= max_turns:
                update_worker_status(task_id, "failed", "Worker hit max turns limit.")
            return False

        await asyncio.wait_for(_run(), timeout=worker_timeout)
        
    except asyncio.TimeoutError:
        update_worker_status(task_id, "failed", f"Worker timed out after {worker_timeout} seconds.")
    except Exception as e:
        logger.exception("Global worker error")
        update_worker_status(task_id, "failed", f"Global worker loop error: {e}")

