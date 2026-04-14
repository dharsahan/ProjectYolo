import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from colorama import Fore, Style, init
from dotenv import load_dotenv

import tools
from llm_router import LLMRouter, load_llm_config
from session import Session

init(autoreset=True)
load_dotenv()

VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

llm_config = load_llm_config()
if not llm_config.model:
    print(f"{Fore.RED}[ERROR] No model configured. Set `MODEL_NAME` or provider-specific model env.")
    sys.exit(1)

router = LLMRouter(llm_config)
_REPO_HAS_TESTS_CACHE: Optional[bool] = None
AUTO_FACTS_START = "[AUTO_BASIC_FACTS]"
AUTO_FACTS_END = "[/AUTO_BASIC_FACTS]"


SELF_UPGRADE_SYSTEM_DIRECTIVE = (
    "SELF-UPGRADE PROTOCOL (MANDATORY FOR THIS REQUEST): "
    "You are being asked to add a new capability to yourself. "
    "Complete these phases before giving a final answer: "
    "(1) Research: use at least one research tool (`web_search`, `browse_url`, browser tools, or `mcp_*`) to gather external guidance. "
    "(2) Implement: modify your own code using file tools. "
    "(3) Validate: run tests/validation with `run_bash` (or at minimum compile checks). "
    "If tests exist in this repository, run at least one `pytest` command. "
    "(4) Evolve memory/skills: record what changed using `learn_experience`, `archive_proactive_memory`, or `self_upgrade_summary`, and update/add a reusable skill with `optimize_skill` or `develop_new_skill` when relevant. "
    "Then provide a concise completion report including what was researched, what was changed, and validation results."
)


EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE = (
    "EXPERIENCE UPDATE PROTOCOL: "
    "When the user asks to update, learn, or record experiences/lessons, "
    "you MUST call `learn_experience` at least once before claiming success. "
    "Do not say experiences were updated unless the tool call has completed."
)


THINK_MODE_SYSTEM_DIRECTIVE = (
    "THINK MODE (COMPLEX TASKS): "
    "For complex or multi-step tasks, first create a concise execution plan, "
    "then execute tools in a deliberate sequence, validating outputs after each major step. "
    "When useful, verify assumptions with quick checks before making irreversible changes. "
    "Prioritize correctness and completeness over speed."
)


def _is_complex_task_prompt(user_msg: str) -> bool:
    msg = (user_msg or "").lower()
    if not msg:
        return False

    multi_step_markers = ["1.", "2.", "first", "second", "then", "after that"]
    complex_keywords = [
        "architecture",
        "refactor",
        "migrate",
        "integrate",
        "multi-step",
        "pipeline",
        "end-to-end",
        "optimize",
        "performance",
        "debug",
        "deploy",
        "production",
        "comprehensive",
    ]

    if any(k in msg for k in complex_keywords):
        return True
    if sum(1 for m in multi_step_markers if m in msg) >= 2:
        return True
    if len(msg.split()) >= 40:
        return True
    return False


def _is_self_upgrade_request(user_msg: str) -> bool:
    msg = user_msg.lower()
    triggers = [
        "new feature for yourself",
        "new feature for itself",
        "improve yourself",
        "upgrade yourself",
        "self-improving",
        "add capability to yourself",
        "write new feature for yourself",
        "write new feature for itself",
    ]
    return any(t in msg for t in triggers)


def _is_experience_update_request(user_msg: str) -> bool:
    msg = user_msg.lower()
    triggers = [
        "update your experiences",
        "update experiences",
        "record this experience",
        "learn from this",
        "remember this lesson",
        "add this to your experiences",
    ]
    return any(t in msg for t in triggers)


def _inject_system_directive(session: Session, directive: str) -> None:
    if not session.message_history or session.message_history[0].get("role") != "system":
        return
    content = session.message_history[0].get("content", "")
    if directive not in content:
        session.message_history[0]["content"] = content + "\n\n" + directive


def _is_memory_context_message(msg: Dict[str, Any]) -> bool:
    if msg.get("role") != "system":
        return False
    content = str(msg.get("content") or "")
    return content.startswith("[MEMORY_CONTEXT]")


def _strip_memory_context_messages(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m for m in history if not _is_memory_context_message(m)]


def _extract_memory_lines(results: Any, limit: int = 6) -> List[str]:
    if isinstance(results, dict):
        results = results.get("results", [])
    if not isinstance(results, list):
        results = [results]

    lines: List[str] = []
    for item in results:
        if isinstance(item, dict):
            text = item.get("memory") or item.get("text") or str(item)
        else:
            text = str(item)
        text = " ".join(text.split())
        if text and text not in lines:
            lines.append(text)
        if len(lines) >= limit:
            break
    return lines


def _derive_identity_hints(memory_lines: List[str]) -> List[str]:
    hints = []
    for line in memory_lines:
        lower = line.lower()
        if "name is " in lower:
            idx = lower.find("name is ")
            value = line[idx + len("name is ") :].strip(" .:-")
            if value:
                hints.append(f"User name: {value}")
                break
    return hints


def _derive_basic_facts(memory_lines: List[str], max_facts: int = 6) -> List[str]:
    facts: List[str] = []
    seen = set()

    def add_fact(value: str) -> None:
        cleaned = " ".join(value.split()).strip(" -\t\n")
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append(cleaned)

    # High-priority identity fact (name)
    for line in memory_lines:
        match = re.search(r"\bname is\s+([a-zA-Z][a-zA-Z0-9 _'\-]{0,50})", line, flags=re.IGNORECASE)
        if match:
            add_fact(f"User name: {match.group(1).strip(' .:-')}")
            break

    # Other compact preference/tooling facts
    for line in memory_lines:
        lower = line.lower().strip()
        if len(facts) >= max_facts:
            break
        if lower.startswith("uses "):
            add_fact(line)
            continue
        if lower.startswith("prefers "):
            add_fact(line)
            continue
        if lower.startswith("wants ") and len(line) <= 140:
            add_fact(line)

    return facts[:max_facts]


def _strip_auto_facts_block(content: str) -> str:
    start = content.find(AUTO_FACTS_START)
    if start == -1:
        return content
    end = content.find(AUTO_FACTS_END, start)
    if end == -1:
        return content[:start].rstrip()
    return (content[:start] + content[end + len(AUTO_FACTS_END) :]).rstrip()


def extract_auto_basic_facts(system_prompt_content: str) -> List[str]:
    start = system_prompt_content.find(AUTO_FACTS_START)
    if start == -1:
        return []
    end = system_prompt_content.find(AUTO_FACTS_END, start)
    if end == -1:
        return []

    block = system_prompt_content[start + len(AUTO_FACTS_START) : end]
    facts: List[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        facts.append(line)
    return facts


def _sync_basic_facts_into_system_prompt(session: Session, memory_service: Any) -> None:
    if not memory_service:
        return
    if not session.message_history or session.message_history[0].get("role") != "system":
        return

    try:
        all_results = memory_service.get_all(user_id=str(session.user_id))
    except Exception:
        return

    memory_lines = _extract_memory_lines(all_results, limit=40)
    facts = _derive_basic_facts(memory_lines, max_facts=6)

    content = session.message_history[0].get("content", "")
    base = _strip_auto_facts_block(content)
    if not facts:
        session.message_history[0]["content"] = base
        return

    facts_block = (
        f"{AUTO_FACTS_START}\n"
        + "\n".join(f"- {fact}" for fact in facts)
        + f"\n{AUTO_FACTS_END}"
    )
    session.message_history[0]["content"] = base.rstrip() + "\n\n" + facts_block


def _build_memory_context(
    memory_service: Any,
    user_id: int,
    user_msg: str,
) -> Optional[str]:
    if not memory_service or not user_msg:
        return None

    try:
        search_results = memory_service.search(user_msg, user_id=str(user_id), limit=8)
    except Exception:
        search_results = []

    try:
        all_results = memory_service.get_all(user_id=str(user_id))
    except Exception:
        all_results = []

    relevant_lines = _extract_memory_lines(search_results, limit=6)
    all_lines = _extract_memory_lines(all_results, limit=20)
    identity_hints = _derive_identity_hints(all_lines)

    sections: List[str] = []
    if identity_hints:
        sections.append("Identity hints:\n" + "\n".join(f"- {h}" for h in identity_hints))
    if relevant_lines:
        sections.append("Relevant long-term memories:\n" + "\n".join(f"- {line}" for line in relevant_lines))

    if not sections:
        return None

    return "[MEMORY_CONTEXT]\n" + "\n\n".join(sections)


def _repo_has_tests() -> bool:
    global _REPO_HAS_TESTS_CACHE
    if _REPO_HAS_TESTS_CACHE is not None:
        return _REPO_HAS_TESTS_CACHE

    root = Path.cwd()
    if (root / "tests").is_dir() or (root / "test").is_dir():
        _REPO_HAS_TESTS_CACHE = True
        return True

    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
    }

    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for name in files:
            lower = name.lower()
            if lower.startswith("test_") and lower.endswith(".py"):
                _REPO_HAS_TESTS_CACHE = True
                return True
            if lower.endswith("_test.py"):
                _REPO_HAS_TESTS_CACHE = True
                return True

    _REPO_HAS_TESTS_CACHE = False
    return False


def _collect_turn_tool_names(history: List[Dict[str, Any]], start_idx: int) -> set[str]:
    names = set()
    for msg in history[start_idx:]:
        if msg.get("role") == "tool":
            name = msg.get("name")
            if name:
                names.add(name)
    return names


def _collect_run_bash_commands(history: List[Dict[str, Any]], start_idx: int) -> List[str]:
    commands: List[str] = []
    for msg in history[start_idx:]:
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = (tc.get("function") or {}).get("name")
            if fn != "run_bash":
                continue
            raw_args = (tc.get("function") or {}).get("arguments", "{}")
            try:
                parsed = json.loads(raw_args)
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                cmd = parsed.get("command")
                if isinstance(cmd, str) and cmd.strip():
                    commands.append(cmd.strip())
    return commands


def _missing_self_upgrade_phases(
    tool_names: set[str],
    run_bash_commands: Optional[List[str]] = None,
    require_pytest: bool = False,
) -> List[str]:
    research_tools = {
        "web_search",
        "browse_url",
        "browser_navigate",
        "browser_extract_text",
        "browser_extract_links",
        "mcp_list_tools",
        "mcp_run_tool",
    }
    implement_tools = {"write_file", "edit_file", "move_file", "copy_file", "make_dir"}
    evolve_tools = {
        "learn_experience",
        "archive_proactive_memory",
        "self_upgrade_summary",
        "optimize_skill",
        "develop_new_skill",
    }

    missing = []
    if not (tool_names & research_tools):
        missing.append("research")
    if not (tool_names & implement_tools):
        missing.append("implementation")
    if "run_bash" not in tool_names:
        missing.append("validation")
    elif require_pytest:
        commands = run_bash_commands or []
        has_pytest = any("pytest" in c.lower() for c in commands)
        if not has_pytest:
            missing.append("validation_pytest")
    if not (tool_names & evolve_tools):
        missing.append("evolution_update")
    return missing

class PendingConfirmationError(Exception):
    def __init__(self, action: str, path: str, tool_call_id: str, tool_args: dict):
        self.action = action
        self.path = path
        self.tool_call_id = tool_call_id
        self.tool_args = tool_args
        super().__init__(f"Pending confirmation for {action}")

def log_agent(user_id: int, tag: str, message: str, color: str = Fore.CYAN):
    if VERBOSE:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{Fore.WHITE}[{user_id}] [{ts}] {color}{Style.BRIGHT}{tag}{Style.NORMAL} {message}")

def get_initial_messages():
    return [{"role": "system", "content": "You are Yolo, an autonomous system controller (Phase 3). Technical identifiers MUST be in `backticks`."}]


def get_background_initial_messages() -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are Yolo running a detached background mission. "
                "Do the task directly and DO NOT call `run_background_mission` again. "
                "If a tool needs user confirmation, skip that action and continue with safe alternatives. "
                "Technical identifiers MUST be in `backticks`."
            ),
        }
    ]


def _extract_tool_path(args: dict) -> str:
    for key in ("path", "src", "dest"):
        value = args.get(key)
        if value:
            return str(value)
    return "(unknown path)"


def _is_destructive_or_sensitive_tool(func_name: str) -> bool:
    destructive = {
        "write_file",
        "edit_file",
        "delete_file",
        "move_file",
        "copy_file",
        "run_bash",
        "memory_wipe",
        "cancel_scheduled_task",
        "optimize_skill",
        "update_user_identity",
    }
    return func_name in destructive


def _is_out_of_scope(args: dict) -> bool:
    cwd = Path.cwd().resolve(strict=False)
    for key in ("path", "src", "dest"):
        value = args.get(key)
        if not value:
            continue
        try:
            resolved = Path(str(value)).expanduser().resolve(strict=False)
        except Exception:
            return True

        try:
            resolved.relative_to(cwd)
        except ValueError:
            return True
    return False

async def execute_tool_direct(func_name: str, func_args: dict, user_id: int, signal_handler: Optional[Callable] = None, session: Any = None) -> str:
    if not isinstance(func_args, dict):
        return f"Error: Invalid arguments for {func_name}; expected object."

    log_agent(user_id, "🔧 TOOL", f"{func_name}({func_args})", Fore.YELLOW)
    tool_map = {
        "read_file": lambda **kw: tools.read_file(confirm_func=lambda a, t: True, **kw),
        "write_file": lambda **kw: tools.write_file(confirm_func=lambda a, t: True, **kw),
        "edit_file": lambda **kw: tools.edit_file(confirm_func=lambda a, t: True, **kw),
        "delete_file": lambda **kw: tools.delete_file(confirm_func=lambda a, t: True, **kw),
        "copy_file": lambda **kw: tools.copy_file(confirm_func=lambda a, t: True, **kw),
        "move_file": lambda **kw: tools.move_file(confirm_func=lambda a, t: True, **kw),
        "list_dir": lambda **kw: tools.list_dir(confirm_func=lambda a, t: True, **kw),
        "make_dir": lambda **kw: tools.make_dir(confirm_func=lambda a, t: True, **kw),
        "file_info": lambda **kw: tools.file_info(confirm_func=lambda a, t: True, **kw),
        "search_in_file": lambda **kw: tools.search_in_file(confirm_func=lambda a, t: True, **kw),
        "send_to_telegram": lambda **kw: tools.send_to_telegram(confirm_func=lambda a, t: True, **kw),
        "run_bash": lambda **kw: tools.run_bash(**kw),
        "list_skills": lambda **kw: tools.list_skills(**kw),
        "read_skill": lambda **kw: tools.read_skill(**kw),
        "develop_new_skill": lambda **kw: tools.develop_new_skill(**kw),
        "optimize_skill": lambda **kw: tools.optimize_skill(**kw),
        "archive_proactive_memory": lambda **kw: tools.archive_proactive_memory(user_id=user_id, **kw),
        "self_upgrade_summary": lambda **kw: tools.self_upgrade_summary(user_id=user_id, **kw),
        "read_user_identity": lambda **kw: tools.read_user_identity(**kw),
        "update_user_identity": lambda **kw: tools.update_user_identity(**kw),
        "web_search": lambda **kw: tools.web_search(**kw),
        "browse_url": lambda **kw: tools.browse_url(**kw),
        "browser_navigate": lambda **kw: tools.browser_navigate(**kw),
        "browser_click": lambda **kw: tools.browser_click(**kw),
        "browser_click_at": lambda **kw: tools.browser_click_at(**kw),
        "browser_press_key": lambda **kw: tools.browser_press_key(**kw),
        "browser_scroll": lambda **kw: tools.browser_scroll(**kw),
        "browser_scroll_until_end": lambda **kw: tools.browser_scroll_until_end(**kw),
        "browser_crawl_step": lambda **kw: tools.browser_crawl_step(**kw),
        "browser_extract_links": lambda **kw: tools.browser_extract_links(**kw),
        "browser_click_next": lambda **kw: tools.browser_click_next(**kw),
        "browser_type": lambda **kw: tools.browser_type(**kw),
        "browser_screenshot": lambda **kw: tools.browser_screenshot(**kw),
        "browser_extract_text": lambda **kw: tools.browser_extract_text(**kw),
        "browser_wait": lambda **kw: tools.browser_wait(**kw),
        "browser_close": lambda **kw: tools.browser_close(**kw),
        "create_mission": lambda **kw: tools.create_mission(**kw),
        "update_mission": lambda **kw: tools.update_mission(**kw),
        "read_mission": lambda **kw: tools.read_mission(**kw),
        "research_queue_urls": lambda **kw: tools.research_queue_urls(**kw),
        "research_enqueue_from_crawl_step": lambda **kw: tools.research_enqueue_from_crawl_step(**kw),
        "research_get_next": lambda **kw: tools.research_get_next(**kw),
        "research_store_summary": lambda **kw: tools.research_store_summary(**kw),
        "research_get_all_summaries": lambda **kw: tools.research_get_all_summaries(**kw),
        "research_clear": lambda **kw: tools.research_clear(**kw),
        "memory_list": lambda **kw: tools.memory_list(user_id=user_id, **kw),
        "memory_wipe": lambda **kw: tools.memory_wipe(user_id=user_id, **kw),
        "memory_add": lambda **kw: tools.memory_add(user_id=user_id, **kw),
        "mcp_list_tools": lambda **kw: tools.mcp_list_tools(**kw),
        "mcp_run_tool": lambda **kw: tools.mcp_run_tool(**kw),
        "run_background_mission": lambda **kw: tools.run_background_mission(
            user_id=user_id,
            mission_coro=lambda tid: run_agent_turn(
                kw.get("objective"),
                Session(user_id=session.user_id, message_history=get_background_initial_messages(), yolo_mode=True),
                signal_handler=signal_handler,
                memory_service=None,
            ),
            **kw,
        ),
        "learn_experience": lambda **kw: tools.learn_experience(user_id=user_id, **kw),
        "list_experiences": lambda **kw: tools.list_experiences(user_id=user_id, **kw),
        "schedule_task": lambda **kw: tools.schedule_task(user_id=user_id, **kw),
        "schedule_daily_task": lambda **kw: tools.schedule_daily_task(user_id=user_id, **kw),
        "get_scheduled_tasks": lambda **kw: tools.get_scheduled_tasks(user_id=user_id, **kw),
        "cancel_scheduled_task": lambda **kw: tools.cancel_scheduled_task(**kw),
        "create_artifact": lambda **kw: tools.create_artifact(**kw),
        "list_artifacts": lambda **kw: tools.list_artifacts(**kw),
        "get_latest_artifact": lambda **kw: tools.get_latest_artifact(**kw),
    }
    if func_name in tool_map:
        import inspect
        res = tool_map[func_name](**func_args)
        if inspect.iscoroutine(res): res = await res
        if res is None:
            res = ""
        if not isinstance(res, str):
            res = str(res)
        if signal_handler and isinstance(res, str) and res.startswith("__SEND_FILE__:"):
            sig = await signal_handler(res)
            if sig: res = sig
        log_agent(user_id, "✅ RESULT", str(res)[:200] + "..." if len(str(res))>200 else str(res), Fore.GREEN)
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
            if expected_ids == found_ids and len(tool_responses) == len(msg["tool_calls"]):
                sanitized.append(msg)
                sanitized.extend(tool_responses)
                i = j
            else:
                # Sequence broken. Strip tool_calls to save text, drop orphaned tool responses
                safe_msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                if not safe_msg.get("content"):
                    safe_msg["content"] = "[Corrupted tool call sequence removed for safety]"
                sanitized.append(safe_msg)
                i = j
        elif msg.get("role") == "tool":
            i += 1 # Drop stray tool responses
        else:
            sanitized.append(msg)
            i += 1
            
    return sanitized

async def run_agent_turn(user_msg: Optional[str], session: Session, signal_handler: Optional[Callable] = None, memory_service: Any = None) -> str:
    self_upgrade_active = False
    self_upgrade_start_index = len(session.message_history)
    experience_update_active = False
    experience_update_start_index = len(session.message_history)

    if not session.message_history:
        session.message_history = get_initial_messages()

    # Keep durable, compact facts in base system prompt.
    _sync_basic_facts_into_system_prompt(session, memory_service)

    # Auto-think behavior: auto policy enables think mode for complex prompts;
    # explicit on/off is controlled by think_mode_policy.
    if getattr(session, "think_mode_policy", "auto") == "auto" and user_msg is not None:
        session.think_mode = _is_complex_task_prompt(user_msg)

    if getattr(session, "think_mode", False):
        _inject_system_directive(session, THINK_MODE_SYSTEM_DIRECTIVE)

    if user_msg:
        # Prevent stale duplication of transient memory context in long sessions.
        session.message_history = _strip_memory_context_messages(session.message_history)

        memory_context = _build_memory_context(memory_service, session.user_id, user_msg)
        if memory_context:
            # Insert after system prompt so it affects the current reasoning turn.
            insert_at = 1 if session.message_history and session.message_history[0].get("role") == "system" else 0
            session.message_history.insert(insert_at, {"role": "system", "content": memory_context})

        if _is_self_upgrade_request(user_msg):
            self_upgrade_active = True
            _inject_system_directive(session, SELF_UPGRADE_SYSTEM_DIRECTIVE)
            self_upgrade_start_index = len(session.message_history)

        if _is_experience_update_request(user_msg):
            experience_update_active = True
            _inject_system_directive(session, EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE)
            experience_update_start_index = len(session.message_history)

        session.message_history.append({"role": "user", "content": user_msg})
        log_agent(session.user_id, "IN", user_msg, Fore.CYAN)

    while True:
        assistant_msg = None
        for msg in reversed(session.message_history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                assistant_msg = msg; break
        
        if assistant_msg:
            answered = {m["tool_call_id"] for m in session.message_history if m.get("role") == "tool"}
            unanswered = [tc for tc in assistant_msg["tool_calls"] if tc["id"] not in answered]

            if unanswered:
                log_agent(session.user_id, "RESUME", f"Completing turn with {len(unanswered)} responses...", Fore.YELLOW)
                hitl_to_raise = None
                for tool_call in unanswered:
                    func_name = tool_call["function"]["name"]
                    tc_id = tool_call["id"]
                    try:
                        args = json.loads(tool_call["function"].get("arguments", "{}"))
                    except Exception:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}

                    if func_name == "run_background_mission" and session is not None:
                        system_prompt = ""
                        if session.message_history and session.message_history[0].get("role") == "system":
                            system_prompt = session.message_history[0].get("content", "")
                        if "detached background mission" in system_prompt.lower():
                            res = "Skipping nested `run_background_mission` call: already running in background mode."
                            session.message_history.append({"role": "tool", "tool_call_id": tc_id, "name": func_name, "content": res})
                            continue

                    out_of_scope = _is_out_of_scope(args)
                    if (_is_destructive_or_sensitive_tool(func_name) or out_of_scope) and not session.yolo_mode:
                        pending_path = _extract_tool_path(args)
                        # PROXY COMPLIANCE: Answer the call with a placeholder so the turn is technically "complete"
                        session.message_history.append({"role": "tool", "tool_call_id": tc_id, "name": func_name, "content": "[HITL_PENDING]"})
                        if not hitl_to_raise:
                            hitl_to_raise = PendingConfirmationError(func_name, pending_path, tc_id, args)
                        continue

                    # Normal execution
                    res = await execute_tool_direct(func_name, args, session.user_id, signal_handler, session=session)
                    session.message_history.append({"role": "tool", "tool_call_id": tc_id, "name": func_name, "content": res})
                
                if hitl_to_raise:
                    session.pending_confirmation = {"action": hitl_to_raise.action, "args": hitl_to_raise.tool_args, "tool_call_id": hitl_to_raise.tool_call_id}
                    raise hitl_to_raise
                continue

        log_agent(session.user_id, "THINKING", "Consulting LLM...", Fore.MAGENTA)
        
        session.message_history = sanitize_history(session.message_history)
        
        try:
            response = await router.chat_completions(
                messages=session.message_history,
                tools=tools.TOOLS_SCHEMAS,
                tool_choice="auto",
            )
        except Exception as e: return f"Error: LLM issue: {e}"

        if not response.choices: return "Error: No AI response."
        msg = response.choices[0].message
        msg_dict = msg.model_dump(exclude_none=True)
        if "content" not in msg_dict or msg_dict["content"] is None: msg_dict["content"] = ""
        session.message_history.append(msg_dict)

        if not msg.tool_calls:
            if self_upgrade_active:
                used_tools = _collect_turn_tool_names(session.message_history, self_upgrade_start_index)
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
                    session.message_history.append({"role": "user", "content": guidance})
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
                    session.message_history.append({"role": "user", "content": guidance})
                    continue

            if memory_service and user_msg:
                try: memory_service.add([{"role":"user","content":user_msg}, {"role":"assistant","content":msg.content}], user_id=str(session.user_id))
                except Exception: pass
            return msg.content or "Task completed."
