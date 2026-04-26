import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from colorama import Fore, Style, init
from dotenv import load_dotenv

import tools
from llm_router import LLMRouter, load_llm_config
from session import Session

class TUIMessage:
    STREAM = "__STREAM__"
    STATUS = "__STATUS__"
    TOOL_CALL = "__TOOL_CALL__"
    TOOL_RESULT = "__TOOL_RESULT__"
    DONE = "__DONE__"

init(autoreset=True)
load_dotenv()

VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

def _get_router() -> LLMRouter:
    """Helper to load configuration and return a router instance."""
    config = load_llm_config()
    if not config.model:
        raise ValueError("No LLM model configured.")
    return LLMRouter(config)

router = _get_router()

def reload_router():
    """Manually reload the global router (useful for tests or env changes)."""
    global router
    router = _get_router()
_REPO_HAS_TESTS_CACHE: Optional[bool] = None
AUTO_FACTS_START = "[AUTO_BASIC_FACTS]"
AUTO_FACTS_END = "[/AUTO_BASIC_FACTS]"
MEMORY_CONTEXT_TRANSIENT_START = "[MEMORY_CONTEXT_TRANSIENT]"
MEMORY_CONTEXT_TRANSIENT_END = "[/MEMORY_CONTEXT_TRANSIENT]"
LEGACY_APPENDIX_START = "[LEGACY_SYSTEM_APPENDIX]"
LEGACY_APPENDIX_END = "[/LEGACY_SYSTEM_APPENDIX]"
AUTO_COMPACT_THRESHOLD = int(os.getenv("AUTO_COMPACT_THRESHOLD", "40"))
PROMPTS_DIR = Path(__file__).resolve().parent / "configs" / "prompts"
_PROMPT_TEMPLATE_CACHE: Dict[str, str] = {}


def _is_small_model_name(model_name: str) -> bool:
    match = re.search(r"(\d+(?:\.\d+)?)b", (model_name or "").lower())
    if not match:
        return False
    try:
        return float(match.group(1)) <= 3.0
    except Exception:
        return False


def _use_unified_prompt_architecture() -> bool:
    version = os.getenv("YOLO_SYSTEM_PROMPT_VERSION", "unified").strip().lower()
    return version not in {"legacy", "v0", "off", "false", "0"}


def _resolve_prompt_profile(profile: Optional[str] = None) -> str:
    explicit = (profile or "").strip().lower()
    if explicit in {"verbose", "compact"}:
        return explicit

    env_profile = os.getenv("YOLO_SYSTEM_PROMPT_PROFILE", "auto").strip().lower()
    if env_profile in {"verbose", "compact"}:
        return env_profile

    config = load_llm_config()
    return "compact" if _is_small_model_name(config.model or "") else "verbose"


def _load_prompt_template(name: str) -> Optional[str]:
    if name in _PROMPT_TEMPLATE_CACHE:
        value = _PROMPT_TEMPLATE_CACHE[name]
        return value or None

    path = PROMPTS_DIR / f"{name}.md"
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        content = ""

    _PROMPT_TEMPLATE_CACHE[name] = content
    return content or None


def _render_prompt_template(
    template: str,
    *,
    basic_facts: Optional[List[str]] = None,
    identity_hints: Optional[List[str]] = None,
) -> str:
    facts = basic_facts or ["(none yet)"]
    hints = identity_hints or ["(none yet)"]

    rendered = template
    rendered = rendered.replace("{{basic_facts}}", "\n".join(f"- {f}" for f in facts))
    rendered = rendered.replace(
        "{{identity_hints}}", "\n".join(f"- {h}" for h in hints)
    )
    return rendered.strip()


def _strip_tag_block(content: str, start_tag: str, end_tag: str) -> str:
    start = content.find(start_tag)
    if start == -1:
        return content
    end = content.find(end_tag, start)
    if end == -1:
        return content[:start].rstrip()
    return (content[:start] + content[end + len(end_tag) :]).rstrip()


def _replace_tag_block(
    content: str,
    start_tag: str,
    end_tag: str,
    body: Optional[str],
) -> str:
    base = _strip_tag_block(content, start_tag, end_tag)
    if not body or not body.strip():
        return base
    return base.rstrip() + f"\n\n{start_tag}\n{body.strip()}\n{end_tag}"


def _extract_memory_context_payload(memory_context: str) -> str:
    lines = (memory_context or "").splitlines()
    if lines and lines[0].strip() == "[MEMORY_CONTEXT]":
        lines = lines[1:]
    return "\n".join(line for line in lines if line.strip()).strip()

async def run_worker_loop(user_id: int, task_id: str, role: str, objective: str, memory_service: Any) -> None:
    """An isolated loop for a specialized worker agent."""
    import uuid
    from tools.base import audit_log
    from tools.database_ops import add_worker_task
    
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
    
    max_turns = 30
    turns = 0
    
    try:
        # Prevent zombie workers by adding a global timeout (30 mins)
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
                        update_worker_status(task_id, "failed", f"Unauthorized: LLM token expired or invalid.")
                    else:
                        update_worker_status(task_id, "failed", f"Worker crashed: {e}")
                    return True # Error handled

            if turns >= max_turns:
                from tools.database_ops import update_worker_status
                update_worker_status(task_id, "failed", "Worker hit max turns limit.")
            return False

        await asyncio.wait_for(_run(), timeout=1800) # 30 minute timeout
    except asyncio.TimeoutError:
        from tools.database_ops import update_worker_status
        update_worker_status(task_id, "failed", "Worker timed out after 30 minutes.")
    except Exception as e:
        from tools.database_ops import update_worker_status
        update_worker_status(task_id, "failed", f"Global worker loop error: {e}")


async def _compact_history(session: Session, router: LLMRouter) -> None:
    if len(session.message_history) <= 10:
        return

    log_agent(
        session.user_id,
        "COMPACT",
        f"Compacting history ({len(session.message_history)} messages)...",
        Fore.YELLOW,
    )

    # Identify system prompt
    system_prompt = None
    if session.message_history and session.message_history[0].get("role") == "system":
        system_prompt = session.message_history[0]

    # Keep last N messages to maintain immediate context
    keep_last = 6
    if system_prompt:
        to_summarize = session.message_history[1:-keep_last]
    else:
        to_summarize = session.message_history[:-keep_last]

    last_messages = session.message_history[-keep_last:]

    if not to_summarize:
        return

    summary_request = (
        "Summarize the following technical conversation history concisely. "
        "Preserve all specific mission objectives, file paths, tool results, "
        "and established project preferences. Use Markdown bullet points."
    )

    try:
        resp = await router.chat_completions(
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior engineer summarizing a project's state.",
                },
                {
                    "role": "user",
                    "content": f"{summary_request}\n\nCONVERSATION HISTORY:\n{json.dumps(to_summarize)}",
                },
            ],
            tools=[],
        )
        
        if not getattr(resp, "choices", None) or not resp.choices:
            log_agent(session.user_id, "ERROR", "Failed to compact history: empty choices returned by LLM.", Fore.RED)
            return

        summary = resp.choices[0].message.content

        new_history = []
        if system_prompt:
            new_history.append(system_prompt)

        new_history.append(
            {"role": "assistant", "content": f"[CONVERSATION_SUMMARY]\n{summary}"}
        )
        new_history.extend(last_messages)

        session.message_history = new_history
        session.history_dirty = True
        log_agent(
            session.user_id, "COMPACT", "History successfully compacted.", Fore.GREEN
        )
    except Exception as e:
        log_agent(session.user_id, "ERROR", f"Failed to compact history: {e}", Fore.RED)


LEGACY_SELF_UPGRADE_SYSTEM_DIRECTIVE = (
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


LEGACY_EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE = (
    "EXPERIENCE UPDATE PROTOCOL: "
    "When the user asks to update, learn, or record experiences/lessons, "
    "you MUST call `learn_experience` at least once before claiming success. "
    "Do not say experiences were updated unless the tool call has completed."
)


LEGACY_THINK_MODE_SYSTEM_DIRECTIVE = (
    "THINK MODE (COMPLEX TASKS): "
    "For complex or multi-step tasks, first create a concise execution plan, "
    "then execute tools in a deliberate sequence, validating outputs after each major step. "
    "When useful, verify assumptions with quick checks before making irreversible changes. "
    "Prioritize correctness and completeness over speed."
)


LEGACY_GUI_PERCEPTION_DIRECTIVE = (
    "GUI INTERACTION PROTOCOL (MANDATORY) - READ CAREFULLY:\n"
    "1. THINK BEFORE YOU ACT: You are operating a real graphical user interface. You cannot see it natively, so you rely on tools. NEVER hallucinate elements or coordinates.\n"
    "2. PERCEIVE FIRST: You MUST call `gui_analyze_screen` BEFORE making any decisions. Read the returned JSON carefully to understand the screen state (windows, elements, coordinates).\n"
    "3. TARGET BY EXACT TEXT: ALWAYS use `gui_find_element` or `gui_click_element` with the EXACT text from your analysis. Do NOT use `gui_mouse_move`/`gui_mouse_click` with raw coordinates unless absolutely necessary.\n"
    "4. VERIFY ACTIONS: After every action, use `gui_observe_transition` or `gui_analyze_screen` again to confirm the action succeeded before proceeding to the next step.\n"
    "5. ADAPT TO FAILURE: If an element is 'not found', DO NOT GUESS. Read the 'visible_elements' list returned by the tool. If the element is not there, it might be off-screen (use `gui_scroll_screen`) or the app might be loading (wait and retry).\n"
    "6. INTELLIGENT SEQUENCING: For multi-step tasks, form a plan. If you open an app, wait for it to appear in the active windows before trying to click inside it."
)


def _load_mode_directive(template_name: str, fallback: str) -> str:
    from_template = _load_prompt_template(template_name)
    return from_template if from_template else fallback


SELF_UPGRADE_SYSTEM_DIRECTIVE = _load_mode_directive(
    "self_upgrade", LEGACY_SELF_UPGRADE_SYSTEM_DIRECTIVE
)
EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE = _load_mode_directive(
    "experience", LEGACY_EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE
)
THINK_MODE_SYSTEM_DIRECTIVE = _load_mode_directive(
    "think", LEGACY_THINK_MODE_SYSTEM_DIRECTIVE
)
GUI_PERCEPTION_DIRECTIVE = LEGACY_GUI_PERCEPTION_DIRECTIVE


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
        "deep",
    ]

    if any(k in msg for k in complex_keywords):
        return True
    if sum(1 for m in multi_step_markers if m in msg) >= 2:
        return True
    if len(msg.split()) >= 40:
        return True
    return False


def _is_gui_interaction_request(user_msg: str) -> bool:
    """Detect if the user wants to interact with the GUI / screen."""
    msg = user_msg.lower()
    triggers = [
        "screen",
        "click",
        "mouse",
        "gui",
        "desktop",
        "window",
        "screenshot",
        "type in",
        "open app",
        "open application",
        "what's on",
        "what is on",
        "look at",
        "see my",
        "scroll",
        "keyboard",
        "press",
        "menu",
        "button",
        "display",
        "monitor",
        "cursor",
    ]
    return any(t in msg for t in triggers)


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
    if (
        not session.message_history
        or session.message_history[0].get("role") != "system"
    ):
        return
    content = session.message_history[0].get("content", "")
    if directive not in content:
        session.message_history[0]["content"] = content + "\n\n" + directive
        # System prompt content changed; sanitize output may differ.
        session.history_dirty = True


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
        match = re.search(
            r"\bname is\s+([a-zA-Z][a-zA-Z0-9 _'\-]{0,50})", line, flags=re.IGNORECASE
        )
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


def _fetch_all_memories(memory_service: Any, user_id: int) -> Any:
    """Single point of access for `memory_service.get_all`. Used by both
    `_sync_basic_facts_into_system_prompt` and `_build_memory_context` so a
    given turn pays the (potentially network/embedding) cost at most once.
    Returns an empty list on error.
    """
    if not memory_service:
        return []
    try:
        # mem0 v2.0.0 requires entity IDs in a filters dict
        return memory_service.get_all(filters={"user_id": str(user_id)})
    except Exception:
        return []


def _sync_basic_facts_into_system_prompt(
    session: Session,
    memory_service: Any,
    *,
    all_results: Any = None,
) -> None:
    if not memory_service:
        return
    if (
        not session.message_history
        or session.message_history[0].get("role") != "system"
    ):
        return

    if all_results is None:
        all_results = _fetch_all_memories(memory_service, session.user_id)

    memory_lines = _extract_memory_lines(all_results, limit=40)
    facts = _derive_basic_facts(memory_lines, max_facts=6)

    content = str(session.message_history[0].get("content") or "")
    facts_body = "\n".join(f"- {fact}" for fact in facts)
    updated = _replace_tag_block(
        content,
        AUTO_FACTS_START,
        AUTO_FACTS_END,
        facts_body,
    )
    if updated != content:
        session.message_history[0]["content"] = updated
        session.history_dirty = True


def _build_memory_context(
    memory_service: Any,
    user_id: int,
    user_msg: str,
    *,
    all_results: Any = None,
) -> Optional[str]:
    if not memory_service or not user_msg:
        return None

    try:
        # mem0 v2.0.0 requires entity IDs in a filters dict
        search_results = memory_service.search(
            user_msg, filters={"user_id": str(user_id)}, limit=8
        )
    except Exception:
        search_results = []

    if all_results is None:
        all_results = _fetch_all_memories(memory_service, user_id)

    relevant_lines = _extract_memory_lines(search_results, limit=6)
    all_lines = _extract_memory_lines(all_results, limit=20)
    identity_hints = _derive_identity_hints(all_lines)

    sections: List[str] = []
    if identity_hints:
        sections.append(
            "Identity hints:\n" + "\n".join(f"- {h}" for h in identity_hints)
        )
    if relevant_lines:
        sections.append(
            "Relevant long-term memories:\n"
            + "\n".join(f"- {line}" for line in relevant_lines)
        )

    if not sections:
        return None

    return "[MEMORY_CONTEXT]\n" + "\n\n".join(sections)


def _repo_has_tests() -> bool:
    """Detect whether the repo has a test suite.

    Performance: result is cached for the process lifetime. Cheap checks
    (top-level `tests/` or `test/` dir) short-circuit. Only when those are
    absent do we fall back to a bounded walk that skips heavy directories
    like `node_modules`, `.venv`, etc. The walk is also depth-limited to
    avoid scanning thousands of files in vendored trees.
    """
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
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "browser_profile",
        "artifacts",
    }

    # Depth-limited walk: tests are conventionally near the project root.
    max_depth = 3
    root_str = str(root)
    for base, dirs, files in os.walk(root):
        rel_depth = base[len(root_str) :].count(os.sep)
        if rel_depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for name in files:
            lower = name.lower()
            if (lower.startswith("test_") and lower.endswith(".py")) or lower.endswith(
                "_test.py"
            ):
                _REPO_HAS_TESTS_CACHE = True
                return True

    _REPO_HAS_TESTS_CACHE = False
    return False


# Performance: precompute at import so the first self-upgrade request
# does not pay the filesystem-walk cost inside the async hot path.
try:
    _repo_has_tests()
except Exception:
    pass


def _collect_turn_tool_names(history: List[Dict[str, Any]], start_idx: int) -> set[str]:
    names = set()
    for msg in history[start_idx:]:
        if msg.get("role") == "tool":
            name = msg.get("name")
            if name:
                names.add(name)
    return names


def _collect_run_bash_commands(
    history: List[Dict[str, Any]], start_idx: int
) -> List[str]:
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
        print(
            f"{Fore.WHITE}[{user_id}] [{ts}] {color}{Style.BRIGHT}{tag}{Style.NORMAL} {message}"
        )
    
    # Also log to audit file for TUI visibility
    from tools.base import audit_log
    audit_log("agent", {"user_id": user_id}, tag, message)


LEGACY_BASE_SYSTEM_PROMPT = (
    "You are Yolo, an elite autonomous system controller and expert software engineer. "
    "You possess intelligence on par with or exceeding the most advanced AI models in the world.\n\n"
    "CORE PRINCIPLES:\n"
    "1. Deep Reasoning: Always think step-by-step. Analyze problems systematically before generating solutions.\n"
    "2. Expert Execution: Write clean, idiomatic, and highly optimized code. Anticipate edge cases and handle errors gracefully.\n"
    "3. Adaptive Self-Correction: If a tool fails or an assumption is wrong, diagnose the root cause instead of blindly retrying.\n"
    "4. Precise Communication: Be concise but highly technical. Technical identifiers MUST be in `backticks`.\n"
    "5. Complete Autonomy: Take ownership of tasks from end-to-end. Do not ask for user permission unless absolutely necessary.\n\n"
    "BEHAVIORAL GUIDELINES (MANDATORY):\n"
    "• SEARCH-FIRST: For any factual question about the present-day world (roles, prices, laws, current status), you MUST use `web_search` before answering. Do not rely on training data for time-sensitive information.\n"
    "• TONE & FORMATTING: Use a warm, constructive tone. Respond in natural prose and paragraphs. Avoid over-formatting with headers, bold text, or bullet points unless essential or explicitly requested. Keep responses brief and focused.\n"
    "• COPYRIGHT COMPLIANCE: Paraphrase search results in your own voice. NEVER quote more than 15 words from a single source. Limit to ONE quote per source; once quoted, a source is CLOSED for further quotation. NEVER reproduce lyrics, poems, or article paragraphs.\n"
    "• NO VOICE NOTES: Never use `<antml:voice_note>` tags in your output.\n"
    "• EVENHANDEDNESS: Stay neutral on political/ethical debates. Provide balanced overviews of opposing views rather than personal opinions.\n"
    "• USER WELLBEING: Handle sensitive topics with care. Avoid encouraging self-destructive behaviors or reinforcing detachment from reality.\n\n"
    "Embrace your role as a top-tier cognitive engine."
)


LEGACY_BACKGROUND_SYSTEM_PROMPT = (
    "You are Yolo running a detached background mission. "
    "Do the task directly and DO NOT call `run_background_mission` again. "
    "If a tool needs user confirmation, skip that action and continue with safe alternatives. "
    "Technical identifiers MUST be in `backticks`."
)


def _build_template_driven_system_prompt(profile: Optional[str] = None) -> str:
    resolved_profile = _resolve_prompt_profile(profile)
    template_name = "base_compact" if resolved_profile == "compact" else "base"
    template = _load_prompt_template(template_name)
    if not template:
        template = (
            LEGACY_BASE_SYSTEM_PROMPT
            + "\n\nAuto Basic Facts\n"
            + AUTO_FACTS_START
            + "\n{{basic_facts}}\n"
            + AUTO_FACTS_END
            + "\n\nIdentity Hints\n{{identity_hints}}"
        )
    return _render_prompt_template(template, basic_facts=[], identity_hints=[])


def get_initial_messages(profile: Optional[str] = None):
    if not _use_unified_prompt_architecture():
        return [{"role": "system", "content": LEGACY_BASE_SYSTEM_PROMPT}]
    return [{"role": "system", "content": _build_template_driven_system_prompt(profile)}]


def get_background_initial_messages() -> List[Dict[str, str]]:
    if not _use_unified_prompt_architecture():
        return [{"role": "system", "content": LEGACY_BACKGROUND_SYSTEM_PROMPT}]

    template = _load_prompt_template("background")
    content = template if template else LEGACY_BACKGROUND_SYSTEM_PROMPT
    return [{"role": "system", "content": content}]


def _merge_memory_context_into_system_prompt(
    session: Session,
    memory_context: Optional[str],
) -> None:
    if not session.message_history:
        session.message_history = get_initial_messages()

    if session.message_history[0].get("role") != "system":
        session.message_history.insert(0, get_initial_messages()[0])
        session.history_dirty = True

    base_content = str(session.message_history[0].get("content") or "")
    payload = _extract_memory_context_payload(memory_context or "")
    merged = _replace_tag_block(
        base_content,
        MEMORY_CONTEXT_TRANSIENT_START,
        MEMORY_CONTEXT_TRANSIENT_END,
        payload,
    )
    if merged != base_content:
        session.message_history[0]["content"] = merged
        session.history_dirty = True


def _normalize_single_system_message(session: Session) -> None:
    if not session.message_history:
        return

    changed = False
    if session.message_history[0].get("role") != "system":
        session.message_history = get_initial_messages() + session.message_history
        changed = True

    primary = session.message_history[0]
    primary_content = str(primary.get("content") or "")
    memory_payloads: List[str] = []
    legacy_appendices: List[str] = []
    normalized: List[Dict[str, Any]] = [primary]

    for msg in session.message_history[1:]:
        if msg.get("role") != "system":
            normalized.append(msg)
            continue

        changed = True
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if content.startswith("[MEMORY_CONTEXT]"):
            payload = _extract_memory_context_payload(content)
            if payload:
                memory_payloads.append(payload)
            continue
        if content.startswith("[CONVERSATION_SUMMARY]"):
            normalized.append({"role": "assistant", "content": content})
            continue
        legacy_appendices.append(content)

    merged = _replace_tag_block(
        primary_content,
        MEMORY_CONTEXT_TRANSIENT_START,
        MEMORY_CONTEXT_TRANSIENT_END,
        "\n\n".join(memory_payloads),
    )
    merged = _replace_tag_block(
        merged,
        LEGACY_APPENDIX_START,
        LEGACY_APPENDIX_END,
        "\n\n".join(legacy_appendices),
    )

    if merged != primary_content:
        primary["content"] = merged
        changed = True

    if changed:
        session.message_history = normalized
        session.history_dirty = True


def _extract_tool_path(args: dict) -> str:
    for key in ("path", "src", "dest", "command", "session_id"):
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
        "terminal_interactive_run",
        "terminal_start",
        "terminal_send",
        "terminal_stop",
        "memory_wipe",
        "cancel_scheduled_task",
        "optimize_skill",
        "update_user_identity",
        "git_commit",
        "git_branch",
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


async def execute_tool_direct(
    func_name: str,
    func_args: Any,
    user_id: int,
    signal_handler: Optional[Callable] = None,
    session: Any = None,
) -> str:
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
            f"{TUIMessage.TOOL_CALL}:{json.dumps({'name': func_name, 'args': func_args})}"
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

    tool_map = {
        "read_file": lambda **kw: tools.read_file(confirm_func=lambda a, t: True, **kw),
        "write_file": lambda **kw: tools.write_file(
            confirm_func=lambda a, t: True, **kw
        ),
        "edit_file": lambda **kw: tools.edit_file(confirm_func=lambda a, t: True, **kw),
        "delete_file": lambda **kw: tools.delete_file(
            confirm_func=lambda a, t: True, **kw
        ),
        "copy_file": lambda **kw: tools.copy_file(confirm_func=lambda a, t: True, **kw),
        "move_file": lambda **kw: tools.move_file(confirm_func=lambda a, t: True, **kw),
        "list_dir": lambda **kw: tools.list_dir(confirm_func=lambda a, t: True, **kw),
        "make_dir": lambda **kw: tools.make_dir(confirm_func=lambda a, t: True, **kw),
        "file_info": lambda **kw: tools.file_info(confirm_func=lambda a, t: True, **kw),
        "search_in_file": lambda **kw: tools.search_in_file(
            confirm_func=lambda a, t: True, **kw
        ),
        "send_to_telegram": lambda **kw: tools.send_to_telegram(
            confirm_func=lambda a, t: True, **kw
        ),
        "run_bash": lambda **kw: tools.run_bash(**kw),
        "terminal_interactive_run": lambda **kw: tools.terminal_interactive_run(**kw),
        "terminal_start": lambda **kw: tools.terminal_start(**kw),
        "terminal_send": lambda **kw: tools.terminal_send(**kw),
        "terminal_read": lambda **kw: tools.terminal_read(**kw),
        "terminal_stop": lambda **kw: tools.terminal_stop(**kw),
        "list_skills": lambda **kw: tools.list_skills(**kw),
        "read_skill": lambda **kw: tools.read_skill(**kw),
        "develop_new_skill": lambda **kw: tools.develop_new_skill(**kw),
        "optimize_skill": lambda **kw: tools.optimize_skill(**kw),
        "archive_proactive_memory": lambda **kw: tools.archive_proactive_memory(
            user_id=user_id, **kw
        ),
        "self_upgrade_summary": lambda **kw: tools.self_upgrade_summary(
            user_id=user_id, **kw
        ),
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
        "research_enqueue_from_crawl_step": lambda **kw: tools.research_enqueue_from_crawl_step(
            **kw
        ),
        "research_get_next": lambda **kw: tools.research_get_next(**kw),
        "research_store_summary": lambda **kw: tools.research_store_summary(**kw),
        "research_get_all_summaries": lambda **kw: tools.research_get_all_summaries(
            **kw
        ),
        "research_clear": lambda **kw: tools.research_clear(**kw),
        "memory_list": lambda **kw: tools.memory_list(user_id=user_id, **kw),
        "memory_wipe": lambda **kw: tools.memory_wipe(user_id=user_id, **kw),
        "memory_add": lambda **kw: tools.memory_add(user_id=user_id, **kw),
        "memory_delete": lambda **kw: tools.memory_delete(**kw),
        "mcp_list_tools": lambda **kw: tools.mcp_list_tools(**kw),
        "mcp_run_tool": lambda **kw: tools.mcp_run_tool(**kw),
        "run_background_mission": lambda **kw: tools.run_background_mission(
            user_id=user_id,
            mission_coro=lambda tid: _run_with_history_sync(tid, kw.get("objective"), session, signal_handler),
            **kw,
        ),
        "dispatch_parallel_agents": lambda **kw: tools.dispatch_parallel_agents(
            user_id=user_id,
            mission_coro=lambda obj, tid: _run_with_history_sync(tid, obj, session, signal_handler),
            **kw,
        ),
        "spawn_worker": lambda **kw: tools.spawn_worker(user_id=user_id, **kw),
        "check_workers": lambda **kw: tools.check_workers(user_id=user_id, **kw),
        "spawn_team_discussion": lambda **kw: tools.spawn_team_discussion(**kw),
        "cancel_all_workers": lambda **kw: tools.cancel_all_workers(user_id=user_id, **kw),
        "report_completion": lambda **kw: tools.report_completion(**kw),
        "request_help": lambda **kw: tools.request_help(**kw),
        "learn_experience": lambda **kw: tools.learn_experience(user_id=user_id, **kw),
        "list_experiences": lambda **kw: tools.list_experiences(user_id=user_id, **kw),
        "schedule_task": lambda **kw: tools.schedule_task(user_id=user_id, **kw),
        "schedule_daily_task": lambda **kw: tools.schedule_daily_task(
            user_id=user_id, **kw
        ),
        "get_scheduled_tasks": lambda **kw: tools.get_scheduled_tasks(
            user_id=user_id, **kw
        ),
        "cancel_scheduled_task": lambda **kw: tools.cancel_scheduled_task(**kw),
        "create_artifact": lambda **kw: tools.create_artifact(**kw),
        "list_artifacts": lambda **kw: tools.list_artifacts(**kw),
        "get_latest_artifact": lambda **kw: tools.get_latest_artifact(**kw),
        "compact_conversation": lambda **kw: _compact_history(session, router),
        "gui_mouse_move": lambda **kw: tools.gui_mouse_move(**kw),
        "gui_mouse_click": lambda **kw: tools.gui_mouse_click(**kw),
        "gui_type_text": lambda **kw: tools.gui_type_text(**kw),
        "gui_press_key": lambda **kw: tools.gui_press_key(**kw),
        "gui_screenshot": lambda **kw: tools.gui_screenshot(**kw),
        "gui_get_screen_size": lambda **kw: tools.gui_get_screen_size(**kw),
        "gui_analyze_screen": lambda **kw: tools.gui_analyze_screen(**kw),
        "gui_find_element": lambda **kw: tools.gui_find_element(**kw),
        "gui_click_element": lambda **kw: tools.gui_click_element(**kw),
        "gui_observe_transition": lambda **kw: tools.gui_observe_transition(**kw),
        "gui_scroll_screen": lambda **kw: tools.gui_scroll_screen(**kw),
        "gui_read_text_at": lambda **kw: tools.gui_read_text_at(**kw),
        "git_status": lambda **kw: tools.git_status(**kw),
        "git_diff": lambda **kw: tools.git_diff(**kw),
        "git_log": lambda **kw: tools.git_log(**kw),
        "git_commit": lambda **kw: tools.git_commit(**kw),
        "git_branch": lambda **kw: tools.git_branch(**kw),
        "git_stash": lambda **kw: tools.git_stash(**kw),
        "codebase_index": lambda **kw: tools.codebase_index(**kw),
        "codebase_search": lambda **kw: tools.codebase_search(**kw),
    }

    from tools.plugin_manager import PLUGIN_HANDLERS

    if PLUGIN_HANDLERS:
        tool_map.update(PLUGIN_HANDLERS)

    if func_name in tool_map:
        import inspect

        # Retry transient errors
        _TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)
        _MAX_RETRIES = 2
        res = None
        for _attempt in range(_MAX_RETRIES + 1):
            try:
                target = tool_map[func_name]
                
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
                f"{TUIMessage.TOOL_RESULT}:{json.dumps({'name': func_name, 'result': res})}"
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


async def run_agent_turn(
    user_msg: Optional[str],
    session: Session,
    signal_handler: Optional[Callable] = None,
    memory_service: Any = None,
) -> str:
    self_upgrade_active = False
    self_upgrade_start_index = len(session.message_history)
    experience_update_active = False
    experience_update_start_index = len(session.message_history)

    if not session.message_history:
        session.message_history = get_initial_messages()

    _normalize_single_system_message(session)

    # Performance: fetch get_all once per turn, share between the two consumers.
    _turn_all_memories = (
        _fetch_all_memories(memory_service, session.user_id) if memory_service else []
    )

    # Keep durable, compact facts in base system prompt.
    _sync_basic_facts_into_system_prompt(
        session, memory_service, all_results=_turn_all_memories
    )

    # Auto-think behavior: auto policy enables think mode for complex prompts;
    # explicit on/off is controlled by think_mode_policy.
    if getattr(session, "think_mode_policy", "auto") == "auto" and user_msg is not None:
        session.think_mode = _is_complex_task_prompt(user_msg)

    if getattr(session, "think_mode", False):
        _inject_system_directive(session, THINK_MODE_SYSTEM_DIRECTIVE)

    if user_msg:
        memory_context = _build_memory_context(
            memory_service, session.user_id, user_msg, all_results=_turn_all_memories
        )
        _merge_memory_context_into_system_prompt(session, memory_context)

        if _is_self_upgrade_request(user_msg):
            self_upgrade_active = True
            _inject_system_directive(session, SELF_UPGRADE_SYSTEM_DIRECTIVE)
            self_upgrade_start_index = len(session.message_history)

        if _is_experience_update_request(user_msg):
            experience_update_active = True
            _inject_system_directive(session, EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE)
            experience_update_start_index = len(session.message_history)

        session.message_history.append({"role": "user", "content": user_msg})
        session.history_dirty = True
        log_agent(session.user_id, "IN", user_msg, Fore.CYAN)

        # Inject GUI perception directive when GUI interaction is detected
        if _is_gui_interaction_request(user_msg):
            _inject_system_directive(session, GUI_PERCEPTION_DIRECTIVE)

    _normalize_single_system_message(session)

    while True:
        assistant_msg = None
        for msg in reversed(session.message_history):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                assistant_msg = msg
                break

        if assistant_msg:
            answered = {
                m["tool_call_id"]
                for m in session.message_history
                if m.get("role") == "tool"
            }
            unanswered = [
                tc for tc in assistant_msg["tool_calls"] if tc["id"] not in answered
            ]

            if unanswered:
                log_agent(
                    session.user_id,
                    "RESUME",
                    f"Completing turn with {len(unanswered)} tool calls...",
                    Fore.YELLOW,
                )

                if signal_handler:
                    tool_names_str = ", ".join(
                        set(tc["function"]["name"] for tc in unanswered)
                    )
                    await signal_handler(
                        f"__STATUS__: Executing tools: {tool_names_str}"
                    )

                # Prepare tasks for parallel execution
                tasks = []
                # Clear previous pending list if we're starting a fresh turn
                # (but technically they should have been resolved already)
                session.pending_confirmations = []

                for tool_call in unanswered:
                    func_name = tool_call["function"]["name"]
                    tc_id = tool_call["id"]
                    try:
                        args = json.loads(tool_call["function"].get("arguments", "{}"))
                    except Exception:
                        args = {}

                    if not isinstance(args, dict):
                        args = {}

                    # Check for nested background missions
                    if func_name == "run_background_mission":
                        system_prompt = ""
                        if (
                            session.message_history
                            and session.message_history[0].get("role") == "system"
                        ):
                            system_prompt = session.message_history[0].get(
                                "content", ""
                            )
                        if "detached background mission" in system_prompt.lower():
                            res = "Skipping nested `run_background_mission` call: already running in background mode."
                            session.message_history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "name": func_name,
                                    "content": res,
                                }
                            )
                            session.history_dirty = True
                            continue

                    # HITL Check
                    out_of_scope = _is_out_of_scope(args)
                    if (
                        _is_destructive_or_sensitive_tool(func_name) or out_of_scope
                    ) and not session.yolo_mode:
                        pending_path = _extract_tool_path(args)
                        # PROXY COMPLIANCE: Answer the call with a placeholder so the turn is technically "complete"
                        session.message_history.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "name": func_name,
                                "content": "[HITL_PENDING]",
                            }
                        )
                        session.history_dirty = True
                        session.pending_confirmations.append(
                            {
                                "action": func_name,
                                "path": pending_path,
                                "args": args,
                                "tool_call_id": tc_id,
                            }
                        )
                        continue

                    # Define the task to be executed
                    async def run_and_store(
                        name=func_name, arguments=args, call_id=tc_id
                    ):
                        result = await execute_tool_direct(
                            name,
                            arguments,
                            session.user_id,
                            signal_handler,
                            session=session,
                        )
                        return {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": name,
                            "content": result,
                        }

                    tasks.append(run_and_store())

                if tasks:
                    # Execute all non-HITL tasks in parallel
                    results = await asyncio.gather(*tasks)
                    session.message_history.extend(results)
                    session.history_dirty = True

                if session.pending_confirmations:
                    if signal_handler:
                        await signal_handler("__STATUS__: ")  # Clear status
                    # Just raise the first one for backwards compat with PendingConfirmationError
                    # but the session now contains ALL of them.
                    first = session.pending_confirmations[0]
                    raise PendingConfirmationError(
                        first["action"],
                        first["path"],
                        first["tool_call_id"],
                        first["args"],
                    )

                continue

        _normalize_single_system_message(session)

        # Auto-compact history if it exceeds threshold
        if len(session.message_history) > AUTO_COMPACT_THRESHOLD:
            await _compact_history(session, router)

        log_agent(session.user_id, "THINKING", "Consulting LLM...", Fore.MAGENTA)
        if signal_handler:
            await signal_handler("__STATUS__: Consulting AI model...")

        # Performance: only sanitize when the history has actually been mutated
        # since the last sanitize. The check is cheap and skipping the O(n)
        # rebuild on every LLM round (especially during multi-step tool loops)
        # noticeably reduces per-turn overhead for long conversations.
        if getattr(session, "history_dirty", True):
            session.message_history = sanitize_history(session.message_history)
            session.history_dirty = False

        try:
            response = await router.chat_completions(
                messages=session.message_history,
                tools=tools.TOOLS_SCHEMAS,
                tool_choice="auto",
                stream=True,
            )
        except Exception as e:
            return f"Error: LLM issue: {e}"

        last_stream_time = 0.0
        full_content = ""
        tool_calls_acc: list = []
        usage = None
        has_choices = False

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage

            if not getattr(chunk, "choices", None):
                continue

            has_choices = True
            delta = chunk.choices[0].delta

            if getattr(delta, "content", None):
                full_content += delta.content
                now = time.time()
                if now - last_stream_time > 0.1 and signal_handler:
                    await signal_handler(f"__STREAM__:{full_content}")
                    last_stream_time = now

            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = getattr(tc, "index", None)
                    if idx is None:
                        idx = 0
                    while len(tool_calls_acc) <= idx:
                        tool_calls_acc.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        )

                    tc_dict = tc.model_dump(exclude_none=True)

                    def _deep_merge(target, source):
                        for k, v in source.items():
                            if k == "index":
                                continue
                            if isinstance(v, dict):
                                if k not in target or not isinstance(target[k], dict):
                                    target[k] = {}
                                _deep_merge(target[k], v)
                            elif (
                                isinstance(v, str)
                                and k in target
                                and isinstance(target[k], str)
                            ):
                                if k in ["name", "arguments", "id"]:
                                    target[k] += v
                                else:
                                    target[k] = v
                            else:
                                target[k] = v

                    _deep_merge(tool_calls_acc[idx], tc_dict)

        if not has_choices and not usage:
            return "Error: No AI response."

        # Final flush of the stream if there was any content
        if full_content and signal_handler:
            await signal_handler(f"__STREAM__:{full_content}")
            await signal_handler("__STREAM_END__:")

        # ── Token / cost tracking ──
        if usage:
            session.total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            session.total_completion_tokens += (
                getattr(usage, "completion_tokens", 0) or 0
            )
            session.total_tokens += getattr(usage, "total_tokens", 0) or 0
        session.llm_call_count += 1

        msg_dict: dict[str, Any] = {"role": "assistant", "content": full_content}
        if tool_calls_acc:
            # Robustness: Filter out tool calls that lack a function name.
            # Also ensure 'arguments' is a valid JSON string (at least "{}")
            # to satisfy strict validation in some OpenAI-compatible proxies (e.g. Ollama).
            valid_tool_calls = []
            for tc in tool_calls_acc:
                if tc.get("function", {}).get("name"):
                    # Ensure arguments is a string (some proxies might return a dict)
                    args = tc["function"].get("arguments")
                    if isinstance(args, dict):
                        tc["function"]["arguments"] = json.dumps(args)
                    elif not args or not isinstance(args, str):
                        tc["function"]["arguments"] = "{}"
                    else:
                        # Optional: attempt to validate JSON to avoid 400s on broken strings
                        try:
                            json.loads(tc["function"]["arguments"])
                        except Exception:
                            # If it's not valid JSON, we default to {} to prevent a 400 error
                            # from the provider on the next turn.
                            tc["function"]["arguments"] = "{}"
                    
                    # Ensure 'id' is not empty if the model failed to provide one
                    if not tc.get("id"):
                        tc["id"] = f"call_{int(time.time()*1000)}"
                        
                    valid_tool_calls.append(tc)
            
            if valid_tool_calls:
                msg_dict["tool_calls"] = valid_tool_calls

        session.message_history.append(msg_dict)
        session.history_dirty = True

        if not tool_calls_acc:
            if self_upgrade_active:
                used_tools = _collect_turn_tool_names(
                    session.message_history, self_upgrade_start_index
                )
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
                    session.message_history.append(
                        {"role": "user", "content": guidance}
                    )
                    session.history_dirty = True
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
                    session.message_history.append(
                        {"role": "user", "content": guidance}
                    )
                    session.history_dirty = True
                    continue

            if memory_service and user_msg:
                try:
                    memory_service.add(
                        [
                            {"role": "user", "content": user_msg},
                            {"role": "assistant", "content": full_content},
                        ],
                        user_id=str(session.user_id),
                    )
                except Exception as e:
                    from tools.base import audit_log
                    audit_log("auto_memory_add", {"user_id": session.user_id}, "error", str(e))

            if signal_handler:
                await signal_handler("__STATUS__: ")  # Clear status
            return full_content or "Task completed."


def main():
    import cli
    cli.main()


if __name__ == "__main__":
    main()
