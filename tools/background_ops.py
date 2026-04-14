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
