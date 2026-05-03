from tools.registry import register_tool
import json
import asyncio
import uuid
from tools.database_ops import update_worker_status, add_worker_task, _conn_ctx
from tools.base import audit_log

@register_tool()
def report_completion(task_id: str, summary: str) -> str:
    """Worker tool: Report that the assigned task is complete."""
    update_worker_status(task_id, "completed", summary)
    audit_log("report_completion", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as completed."

@register_tool()
def request_help(task_id: str, reason: str, context: str) -> str:
    """Worker tool: Report confusion and request Manager assistance."""
    details = json.dumps({"reason": reason, "context": context})
    update_worker_status(task_id, "needs_help", details)
    audit_log("request_help", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as needs_help."

@register_tool()
async def spawn_worker(user_id: int, role: str, objective: str) -> str:
    """Manager tool: Spawn an isolated worker agent for a specific sub-task."""
    task_id = f"w_{uuid.uuid4().hex[:8]}"
    add_worker_task(task_id, user_id, role, objective)
    
    # We need to dispatch the async loop. 
    # Since tools are mostly sync in their signature but executed async by execute_tool_direct, 
    # we use asyncio.create_task to fire and forget.
    from worker import run_worker_loop
    from tools.memory_service import get_memory
    
    loop = asyncio.get_running_loop()
    loop.create_task(run_worker_loop(user_id, task_id, role, objective, get_memory()))
    
    audit_log("spawn_worker", {"task_id": task_id, "role": role}, "success")
    return f"Worker spawned with Task ID: `{task_id}`. Role: {role}. Use `check_workers()` to monitor status."

@register_tool()
def check_workers(user_id: int) -> str:
    """Manager tool: Check the status of all active and recently completed workers."""
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        # Fetch tasks that start with w_ to identify workers vs standard bg tasks
        cursor.execute(
            "SELECT task_id, objective, status, result FROM background_tasks WHERE user_id = ? AND task_id LIKE 'w_%' ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        rows = cursor.fetchall()
    
    if not rows:
        return "No workers found."
        
    output = []
    for r in rows:
        res_preview = (r[3][:100] + "...") if r[3] and len(r[3]) > 100 else (r[3] or "None")
        output.append(f"- ID: {r[0]} | Status: {r[2]} | Obj: {r[1]}\n  Result/Help: {res_preview}")
        
    return "\n".join(output)

@register_tool()
async def spawn_team_discussion(topic: str, roles: list[str], max_rounds: int = 5) -> str:
    """Manager tool: Spawn a synchronous chat room where specialized agents debate a topic until consensus."""
    from agent import router
    
    transcript = [f"**MANAGER**: We need to discuss the following topic to reach a consensus or solution:\n{topic}\n"]
    
    # Initialize histories for each role
    participants = {}
    for role in roles:
        sys_prompt = (
            f"You are participating in an engineering team discussion as the: {role}.\n"
            "Review the transcript of the conversation so far, and provide your expert perspective, critique, or proposal.\n"
            "Be concise and technical. If you agree a consensus has been reached, state 'CONSENSUS REACHED'.\n"
            "Do NOT use tools. Just speak."
        )
        participants[role] = [{"role": "system", "content": sys_prompt}]
        
    rounds = 0
    while rounds < max_rounds:
        rounds += 1
        round_transcript = "\n".join(transcript)
        
        consensus_count = 0
        
        for role, history in participants.items():
            # Build specific prompt for this turn
            prompt = f"Here is the discussion so far:\n\n{round_transcript}\n\nWhat is your input {role}?"
            temp_history = history + [{"role": "user", "content": prompt}]
            
            try:
                response = await router.chat_completions(
                    messages=temp_history,
                    tools=None, # No tools in the chat room
                    tool_choice="none",
                    stream=False
                )
                if not getattr(response, "choices", None) or len(response.choices) == 0:
                    reply = "[No response generated]"
                else:
                    reply = response.choices[0].message.content

                # Save their own thought to their history
                history.append({"role": "user", "content": prompt})
                history.append({"role": "assistant", "content": reply})
                
                transcript.append(f"**{role.upper()}**:\n{reply}\n")
                
                if "CONSENSUS REACHED" in reply.upper():
                    consensus_count += 1
                    
            except Exception as e:
                transcript.append(f"**{role.upper()}** (Error): {e}\n")
                
        if consensus_count == len(roles):
            transcript.append("\n**SYSTEM**: All participants reached consensus. Discussion concluded.")
            break
            
    if rounds >= max_rounds:
        transcript.append("\n**SYSTEM**: Maximum rounds reached. Discussion terminated by timeout.")
        
    audit_log("spawn_team_discussion", {"topic": topic, "roles": roles}, "success")
    return "\n".join(transcript)

@register_tool()
def cancel_all_workers(user_id: int) -> str:
    """Manager tool: Forcefully cancel all currently 'running' workers for the user."""
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE background_tasks SET status = 'cancelled', result = 'Terminated by manager' WHERE user_id = ? AND status = 'running'",
            (user_id,)
        )
        count = cursor.rowcount
    
    audit_log("cancel_all_workers", {"count": count}, "success")
    return f"Successfully cancelled {count} running workers."
