import asyncio
import uuid
import logging
from typing import Any, Callable
from tools.database_ops import add_background_task, update_background_task

logger = logging.getLogger(__name__)

async def run_background_mission(user_id: int, objective: str, mission_coro: Callable) -> str:
    """Spawn a long-running mission in the background and return a Task ID."""
    task_id = str(uuid.uuid4())[:8] # Short unique ID
    
    # Record in DB as running
    add_background_task(task_id, user_id, objective)
    
    # Create the background worker
    async def worker():
        try:
            logger.info(f"Starting background mission {task_id}: {objective}")
            # The coro should be a function that takes task_id and returns a result string
            result = await mission_coro(task_id)
            update_background_task(task_id, "completed", result)
            logger.info(f"Background mission {task_id} completed.")
        except Exception as e:
            logger.error(f"Background mission {task_id} failed: {e}")
            update_background_task(task_id, "failed", str(e))

    # Fire and forget
    asyncio.create_task(worker())
    
    return f"Mission started in the background. Task ID: `{task_id}`. I will notify you when it's done."

async def dispatch_parallel_agents(user_id: int, objectives: list[str], mission_coro: Callable) -> str:
    """Run multiple agents in parallel for different objectives and wait for all results."""
    if not objectives:
        return "No objectives provided."

    logger.info(f"Dispatching {len(objectives)} parallel agents for user {user_id}")
    
    tasks = []
    for i, objective in enumerate(objectives):
        # We reuse the mission_coro but we need to give it a task_id if it expects one
        # but here we just want the result string directly.
        tasks.append(mission_coro(objective))
    
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = [f"### Results for {len(objectives)} Parallel Agents:"]
        for i, (objective, result) in enumerate(zip(objectives, results)):
            if isinstance(result, Exception):
                res_str = f"Error: {str(result)}"
            else:
                res_str = str(result)
            output.append(f"\n#### Agent {i+1}: {objective}\n{res_str}")
        
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Failed to dispatch parallel agents: {e}")
        return f"Error dispatching parallel agents: {e}"
