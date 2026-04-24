import asyncio
import uuid
import logging
from typing import Any, Callable
from tools.database_ops import add_background_task, update_background_task

logger = logging.getLogger(__name__)


async def run_background_mission(
    user_id: int, objective: str, mission_coro: Callable
) -> str:
    """Spawn a long-running mission in the background and return a Task ID."""
    task_id = str(uuid.uuid4())[:8]  # Short unique ID

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


async def dispatch_parallel_agents(
    user_id: int,
    objectives: list[str],
    mission_coro: Callable,
    wait_for_completion: bool = False,
) -> str:
    """Spawn multiple tracked agents in parallel; optionally wait for completion."""
    if not objectives:
        return "No objectives provided."

    logger.info(f"Dispatching {len(objectives)} parallel agents for user {user_id}")

    task_specs: list[tuple[str, str, int]] = []
    for index, objective in enumerate(objectives, start=1):
        task_id = str(uuid.uuid4())[:8]
        labeled_objective = f"[parallel:{index}/{len(objectives)}] {objective}"
        add_background_task(task_id, user_id, labeled_objective)
        task_specs.append((task_id, objective, index))

    async def worker(task_id: str, objective: str, index: int):
        try:
            logger.info(
                "Starting parallel agent %s/%s (%s): %s",
                index,
                len(objectives),
                task_id,
                objective,
            )
            result = await mission_coro(objective)
            update_background_task(task_id, "completed", str(result))
            logger.info("Parallel agent %s completed (%s)", index, task_id)
            return (task_id, objective, result)
        except Exception as e:
            logger.error("Parallel agent %s failed (%s): %s", index, task_id, e)
            update_background_task(task_id, "failed", str(e))
            return (task_id, objective, e)

    workers = [worker(task_id, objective, index) for task_id, objective, index in task_specs]

    if wait_for_completion:
        results = await asyncio.gather(*workers, return_exceptions=False)
        output = [f"### Results for {len(objectives)} Parallel Agents:"]
        for i, (task_id, objective, result) in enumerate(results, start=1):
            if isinstance(result, Exception):
                res_str = f"Error: {str(result)}"
            else:
                res_str = str(result)
            output.append(f"\n#### Agent {i}: {objective}\nTask ID: `{task_id}`\n{res_str}")
        return "\n".join(output)

    for coro in workers:
        asyncio.create_task(coro)

    lines = [
        f"Launched {len(task_specs)} parallel background agents.",
        "Track status with `list_background_tasks`.",
        "Task assignments:",
    ]
    for task_id, objective, index in task_specs:
        lines.append(f"{index}. `{task_id}` -> {objective}")
    return "\n".join(lines)
