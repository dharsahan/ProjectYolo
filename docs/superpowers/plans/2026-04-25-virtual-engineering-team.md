# Virtual Engineering Team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a hybrid Manager-Worker multi-agent architecture where the Manager (YOLO) can spawn isolated Workers for sub-tasks, and initiate a Peer-to-Peer "Chat Room" discussion when a Worker gets stuck.

**Architecture:** 
1. **Manager-Worker**: The main agent (Manager) uses a new tool `spawn_worker` to start an isolated background agent loop. The worker uses `report_completion` or `request_help` to end its loop and return status to the Manager.
2. **Chat Room**: If a worker requests help, the Manager uses `spawn_team_discussion`. This creates a temporary shared transcript where multiple specialized agents (e.g., Architect, Security, the stuck Worker) take turns responding until the Manager concludes the discussion.
3. **State Management**: Workers run as async tasks tracking their state in the SQLite DB (similar to existing background missions but with bidirectional signaling).

**Tech Stack:** Python `asyncio`, SQLite (existing `database_ops.py`), LiteLLM.

---

### Task 1: Core Worker Tools & Database Updates

We need to track worker states and provide tools for them to report back.

**Files:**
- Modify: `tools/database_ops.py`
- Create: `tools/team_ops.py` (New module for team coordination)
- Modify: `tools/__init__.py`

- [ ] **Step 1: Write failing tests for worker DB operations**

```python
# tests/test_team_ops.py
import pytest
from tools.database_ops import add_worker_task, get_worker_status, update_worker_status

def test_worker_lifecycle():
    task_id = "test_w_1"
    add_worker_task(task_id, 123, "Backend", "Fix DB")
    status = get_worker_status(task_id)
    assert status["status"] == "running"
    
    update_worker_status(task_id, "needs_help", "I don't understand the schema")
    status = get_worker_status(task_id)
    assert status["status"] == "needs_help"
    assert status["result"] == "I don't understand the schema"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_team_ops.py -v`
Expected: FAIL with ImportError or undefined functions.

- [ ] **Step 3: Implement DB ops in `tools/database_ops.py`**

```python
# Add to tools/database_ops.py
def add_worker_task(task_id: str, user_id: int, role: str, objective: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO background_tasks (task_id, user_id, objective, status) VALUES (?, ?, ?, ?)",
        (task_id, user_id, f"[{role}] {objective}", "running"),
    )
    conn.commit()
    conn.close()

def get_worker_status(task_id: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, result FROM background_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"status": row[0], "result": row[1]}
    return {"status": "not_found", "result": None}

def update_worker_status(task_id: str, status: str, result: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE background_tasks SET status = ?, result = ? WHERE task_id = ?",
        (status, result, task_id),
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Create `tools/team_ops.py` and implement Worker Tools**

```python
# tools/team_ops.py
import json
from tools.database_ops import update_worker_status
from tools.base import audit_log

def report_completion(task_id: str, summary: str) -> str:
    """Worker tool: Report that the assigned task is complete."""
    update_worker_status(task_id, "completed", summary)
    audit_log("report_completion", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as completed."

def request_help(task_id: str, reason: str, context: str) -> str:
    """Worker tool: Report confusion and request Manager assistance."""
    details = json.dumps({"reason": reason, "context": context})
    update_worker_status(task_id, "needs_help", details)
    audit_log("request_help", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as needs_help."
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_team_ops.py -v`
Expected: PASS

- [ ] **Step 6: Register in `tools/__init__.py`**

```python
# Add to tools/__init__.py imports and __all__
from tools.team_ops import report_completion, request_help

# Add to TOOLS_SCHEMAS (Note: These will be dynamically added to worker prompts, but good to have registered)
    {
        "type": "function",
        "function": {
            "name": "report_completion",
            "description": "Report that your assigned sub-task is successfully complete. This ends your execution loop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Summary of changes made"}
                },
                "required": ["task_id", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_help",
            "description": "Report that you are confused, stuck, or blocked. This pauses your execution so the Manager can intervene or spawn a team discussion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "reason": {"type": "string", "description": "Why you are stuck"},
                    "context": {"type": "string", "description": "Relevant file paths or errors"}
                },
                "required": ["task_id", "reason", "context"]
            }
        }
    },
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_team_ops.py tools/database_ops.py tools/team_ops.py tools/__init__.py
git commit -m "feat(team): add core worker state tracking and reporting tools"
```

---

### Task 2: The Worker Execution Loop

Implement the isolated execution loop for a worker agent.

**Files:**
- Modify: `agent.py`

- [ ] **Step 1: Write `run_worker_turn` in `agent.py`**

```python
# Add to agent.py
async def run_worker_loop(user_id: int, task_id: str, role: str, objective: str, memory_service: Any) -> None:
    """An isolated loop for a specialized worker agent."""
    from session import Session
    import uuid
    from tools.base import audit_log
    
    worker_session = Session(user_id=user_id)
    
    system_prompt = (
        f"You are a specialized worker agent taking on the role of: {role}.\n"
        f"Your specific objective is: {objective}\n"
        f"Your Task ID is: {task_id}\n\n"
        "You operate in an isolated context. You have access to all coding and research tools.\n"
        "CRITICAL: When you have finished the objective, you MUST call `report_completion(task_id, summary)`.\n"
        "CRITICAL: If you are confused, stuck (e.g. failing tests 3+ times), or blocked by architecture, you MUST call `request_help(task_id, reason, context)`.\n"
        "Do NOT ask the user for input. You run autonomously."
    )
    
    worker_session.message_history = [{"role": "system", "content": system_prompt}]
    
    max_turns = 30
    turns = 0
    
    router = _get_router()
    
    while turns < max_turns:
        turns += 1
        try:
            response = await router.chat_completions(
                messages=worker_session.message_history,
                tools=tools.TOOLS_SCHEMAS,
                tool_choice="auto",
                stream=False
            )
            
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
                result = await execute_tool_direct(
                    tc.function.name, 
                    tc.function.arguments, 
                    user_id, 
                    signal_handler=None, 
                    session=worker_session
                )
                
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
            update_worker_status(task_id, "failed", f"Worker crashed: {e}")
            break
            
    if turns >= max_turns:
        from tools.database_ops import update_worker_status
        update_worker_status(task_id, "failed", "Worker hit max turns limit.")
```

- [ ] **Step 2: Commit**

```bash
git add agent.py
git commit -m "feat(team): implement isolated autonomous worker execution loop"
```

---

### Task 3: Manager Tools (`spawn_worker` and `check_workers`)

Give the Manager the ability to start these workers and check on them.

**Files:**
- Modify: `tools/team_ops.py`
- Modify: `tools/__init__.py`

- [ ] **Step 1: Implement `spawn_worker` and `check_workers` in `tools/team_ops.py`**

```python
# Add to tools/team_ops.py
import asyncio
import uuid
from tools.database_ops import add_worker_task, get_db_connection

def spawn_worker(user_id: int, role: str, objective: str) -> str:
    """Manager tool: Spawn an isolated worker agent for a specific sub-task."""
    task_id = f"w_{uuid.uuid4().hex[:8]}"
    add_worker_task(task_id, user_id, role, objective)
    
    # We need to dispatch the async loop. 
    # Since tools are mostly sync in their signature but executed async by execute_tool_direct, 
    # we use asyncio.create_task to fire and forget.
    from agent import run_worker_loop
    from tools.memory_service import get_memory
    
    loop = asyncio.get_running_loop()
    loop.create_task(run_worker_loop(user_id, task_id, role, objective, get_memory()))
    
    audit_log("spawn_worker", {"task_id": task_id, "role": role}, "success")
    return f"Worker spawned with Task ID: `{task_id}`. Role: {role}. Use `check_workers()` to monitor status."

def check_workers(user_id: int) -> str:
    """Manager tool: Check the status of all active and recently completed workers."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch tasks that start with w_ to identify workers vs standard bg tasks
    cursor.execute(
        "SELECT task_id, objective, status, result FROM background_tasks WHERE user_id = ? AND task_id LIKE 'w_%' ORDER BY id DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "No workers found."
        
    output = []
    for r in rows:
        res_preview = (r[3][:100] + "...") if r[3] and len(r[3]) > 100 else (r[3] or "None")
        output.append(f"- ID: {r[0]} | Status: {r[2]} | Obj: {r[1]}\n  Result/Help: {res_preview}")
        
    return "\n".join(output)
```

- [ ] **Step 2: Update schemas in `tools/__init__.py`**

```python
# Add to tools/__init__.py imports and __all__
from tools.team_ops import spawn_worker, check_workers

# Add to TOOLS_SCHEMAS
    {
        "type": "function",
        "function": {
            "name": "spawn_worker",
            "description": "Spawn an isolated worker agent to handle a specific sub-task in the background. Useful for dividing and conquering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "The persona/role (e.g. 'Database Expert', 'Frontend Dev')"},
                    "objective": {"type": "string", "description": "Clear, detailed instructions for what the worker must accomplish."}
                },
                "required": ["role", "objective"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_workers",
            "description": "Check the status of all spawned workers. Use this to see if they are 'completed', 'running', or 'needs_help'.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
```

- [ ] **Step 3: Modify `execute_tool_direct` in `agent.py` to handle passing `user_id` to `spawn_worker`**

```python
# In agent.py, inside execute_tool_direct, update the kwargs logic:
    if action == "run_background_mission":
        kwargs["user_id"] = user_id
    elif action == "dispatch_parallel_agents":
        kwargs["user_id"] = user_id
    elif action == "spawn_worker":
        kwargs["user_id"] = user_id
    elif action == "check_workers":
        kwargs["user_id"] = user_id
```

- [ ] **Step 4: Commit**

```bash
git add tools/team_ops.py tools/__init__.py agent.py
git commit -m "feat(team): add spawn_worker and check_workers manager tools"
```

---

### Task 4: The Chat Room (`spawn_team_discussion`)

Implement the multi-agent peer-to-peer discussion forum.

**Files:**
- Modify: `tools/team_ops.py`
- Modify: `tools/__init__.py`
- Modify: `agent.py`

- [ ] **Step 1: Implement `spawn_team_discussion` in `tools/team_ops.py`**

```python
# Add to tools/team_ops.py
async def spawn_team_discussion(topic: str, roles: list[str], max_rounds: int = 5) -> str:
    """Manager tool: Spawn a synchronous chat room where specialized agents debate a topic until consensus."""
    from agent import _get_router
    router = _get_router()
    
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
```

- [ ] **Step 2: Update `execute_tool_direct` to await async tool**

Because `spawn_team_discussion` is an `async def` function doing LLM calls, `agent.execute_tool_direct` must handle it properly (just like it handles `run_background_mission`).

```python
# In agent.py, execute_tool_direct:
    # Add to the async execution check
    if action == "run_background_mission":
        # existing code...
    elif action == "spawn_team_discussion":
        return await tools.spawn_team_discussion(**kwargs)
```

- [ ] **Step 3: Register in `tools/__init__.py`**

```python
# Add to tools/__init__.py imports and __all__
from tools.team_ops import spawn_team_discussion

# Add to TOOLS_SCHEMAS
    {
        "type": "function",
        "function": {
            "name": "spawn_team_discussion",
            "description": "Start a peer-to-peer chat room discussion among virtual experts to solve a complex problem or unblock a worker. Returns the full transcript of the debate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The problem, context, and what needs to be decided."},
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of personas to invite (e.g. ['Security Expert', 'Stuck Backend Worker', 'Database Architect'])"
                    },
                    "max_rounds": {"type": "integer", "description": "Max turns they take to debate (default 3, max 5)"}
                },
                "required": ["topic", "roles"]
            }
        }
    },
```

- [ ] **Step 4: Commit**

```bash
git add tools/team_ops.py tools/__init__.py agent.py
git commit -m "feat(team): implement spawn_team_discussion for peer-to-peer problem solving"
```

---
