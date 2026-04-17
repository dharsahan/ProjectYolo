# Draft Security Report

## VULN-001: Information Disclosure of Secrets via `read_file`
- **Severity**: Critical
- **Location**: `agent.py`, `tools/file_ops.py`
- **Description**: The `read_file` tool is not classified as a "destructive" or "sensitive" tool in `agent.py`. Additionally, the `.env` file is located within the current working directory, making it "in-scope" for the sandbox check. As a result, an attacker can trick the AI into reading the `.env` file, which contains sensitive API keys and bot tokens, without any human-in-the-loop (HITL) confirmation.
- **Line Content**: `if (_is_destructive_or_sensitive_tool(func_name) or out_of_scope) and not session.yolo_mode:`

## VULN-002: Unrestricted GUI Control Bypassing HITL
- **Severity**: Critical
- **Location**: `agent.py`, `tools/gui_ops.py`
- **Description**: Several powerful GUI manipulation tools (`gui_mouse_move`, `gui_mouse_click`, `gui_type_text`, `gui_press_key`) are not included in the `destructive` tools list in `agent.py`. This allows an attacker (via indirect prompt injection) to control the user's host system (typing commands, opening browsers, exfiltrating data) without any HITL confirmation, even when "Safe Mode" is enabled.
- **Line Content**: `def _is_destructive_or_sensitive_tool(func_name: str) -> bool:`

## VULN-003: Command Injection in `run_bash`
- **Severity**: High
- **Location**: `tools/system_ops.py`
- **Description**: The `run_bash` tool executes arbitrary shell commands on the host system by default. While it is protected by HITL confirmation in Safe Mode, if the user enables "Yolo Mode", the system is highly vulnerable to compromise via indirect prompt injection if the Docker sandbox is not enabled.
- **Line Content**: `result = subprocess.run(["bash", "-c", command], ...)`

## VULN-004: Potential Denial of Service (DoS) in Parallel Agent Dispatch
- **Severity**: High
- **Location**: `tools/background_ops.py`
- **Description**: The `dispatch_parallel_agents` function spawns multiple agents in parallel based on a user-provided list of objectives. There is no limit on the number of parallel agents, which can lead to resource exhaustion (CPU, memory, and API tokens) if exploited.
- **Line Content**: `for i, objective in enumerate(objectives): tasks.append(mission_coro(objective))`

## VULN-005: Broken Access Control (IDOR) in Memory Deletion
- **Severity**: Medium
- **Location**: `tools/memory_ops.py`
- **Description**: The `memory_delete` function accepts a `memory_id` but does not verify if the memory belongs to the requesting user. In a multi-user environment, this allows an authorized user to delete memories belonging to others if they can guess or obtain the memory UUID.
- **Line Content**: `memory.delete(memory_id=memory_id)`

## VULN-006: Privacy Violation: Sensitive Data in Logs
- **Severity**: Medium
- **Location**: `agent.py`, `bot.py`, `tools/memory_ops.py`
- **Description**: The application logs user messages, tool results, and memory facts directly to stdout and log files. If these contain sensitive information like passwords, PII, or API keys, they are exposed in the logs.
- **Line Content**: `log_agent(session.user_id, "IN", user_msg, Fore.CYAN)`

## VULN-007: Sensitive Data Exposure in Database
- **Severity**: Medium
- **Location**: `tools/database_ops.py`
- **Description**: The SQLite database stores conversation history, background mission objectives, and results in plain text. If the database file is compromised, all sensitive information within the conversations is exposed.
- **Line Content**: `cursor.execute("CREATE TABLE IF NOT EXISTS sessions (..., history TEXT, ...)")`

## VULN-008: Markdown Injection in Telegram Output
- **Severity**: Low
- **Location**: `bot.py`
- **Description**: The bot uses `ParseMode.MARKDOWN` to send messages. An attacker could craft malicious content that, when processed by the LLM and sent back to the user, renders misleading links or formatting, potentially used for phishing.
- **Line Content**: `await context.bot.send_message(chat_id, part, parse_mode=ParseMode.MARKDOWN)`
