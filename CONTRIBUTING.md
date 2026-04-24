# Contributing to ProjectYolo

Thanks for your interest in contributing! ProjectYolo is an autonomous AI agent built for real desktop control and software engineering tasks. This guide will get you up and running fast.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [How to Add a New Tool](#how-to-add-a-new-tool)
- [How to Add a New LLM Provider](#how-to-add-a-new-llm-provider)
- [Good First Issues](#good-first-issues)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Code Style](#code-style)
- [Reporting Bugs](#reporting-bugs)

---

## Getting Started

### Prerequisites

- Python 3.9+
- Tesseract OCR

```bash
# Linux
sudo apt install tesseract-ocr

# macOS
brew install tesseract

# Windows
# Download from https://github.com/UB-Mannheim/tesseract/wiki
# Add tesseract.exe to your System PATH
```

### Local Setup

```bash
# 1. Fork and clone the repo
git clone https://github.com/<your-username>/ProjectYolo.git
cd ProjectYolo

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add at minimum one LLM provider key (OPENAI_API_KEY or ANTHROPIC_API_KEY)
```

### Run the agent

```bash
# CLI (quickest way to test)
python cli.py

# Telegram bot
python bot.py

# Discord bot
python discord_gateway.py

# All gateways + health monitor
python server.py --mode all
```

---

## Project Structure

```
ProjectYolo/
├── agent.py              # Core cognitive loop (YOLO / Safe / Think modes)
├── llm_router.py         # LLM provider abstraction — add new providers here
├── session.py            # Message history and context window management
├── bot.py                # Telegram gateway
├── discord_gateway.py    # Discord gateway
├── cli.py                # Terminal interface
├── server.py             # Multi-gateway server
├── tools/                # All agent capabilities live here
│   ├── base.py           # Shared utilities: path resolution, audit logging, mem0 config
│   ├── file_ops.py       # File read/write/search
│   ├── browser_ops.py    # Web browsing via camoufox
│   ├── gui_ops.py        # Screen perception and desktop interaction
│   ├── memory_ops.py     # Long-term memory (mem0)
│   ├── experience_ops.py # Engineering experience log
│   ├── git_ops.py        # Git operations
│   ├── system_ops.py     # Shell and OS commands
│   ├── research_ops.py   # Deep research workflows
│   └── ...               # More tools
├── configs/
│   ├── identity.md       # Agent identity and personality
│   └── prompts/          # System prompt templates
├── skills/               # Reusable agent skill definitions
└── artifacts/            # Agent-generated deliverables
```

---

## How to Add a New Tool

The `tools/` folder is the easiest place to contribute. Each file is a self-contained module exposing plain Python functions.

### Steps

**1. Create your file** — e.g. `tools/calendar_ops.py`

```python
from tools.base import audit_log

def get_events(date: str) -> str:
    """Fetch calendar events for a given date."""
    try:
        # Your implementation here
        result = "..."
        audit_log("get_events", {"date": date}, "success")
        return result
    except Exception as e:
        audit_log("get_events", {"date": date}, "error", str(e))
        return f"{type(e).__name__}: {e}"
```

**2. Register it in `tools/__init__.py`**

```python
from tools.calendar_ops import get_events
```

**3. Add a tool definition in `agent.py`** — find the `tools` list and add an entry:

```python
{
    "type": "function",
    "function": {
        "name": "get_events",
        "description": "Fetch calendar events for a given date. Input: ISO date string.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO 8601 date e.g. 2026-04-24"}
            },
            "required": ["date"],
        },
    },
},
```

**4. Handle the tool call in the agent's dispatch block** — search for `elif tool_name ==` and add your case.

### Guidelines for tools

- Always call `audit_log()` on success and error — this keeps the agent's `agent_log.txt` consistent
- Use `resolve_and_verify_path()` from `base.py` for any file system access
- Return plain strings — the agent reads your output directly
- Keep each function focused on one action
- Add a `confirm_func` parameter for any destructive operation (delete, overwrite, send)

---

## How to Add a New LLM Provider

Open `llm_router.py` and follow this pattern:

**1. Add a default model** in `_default_model()`:

```python
def _default_model(provider: str) -> str:
    defaults = {
        ...
        "gemini": "gemini-2.0-flash",   # add your provider here
    }
```

**2. Add a config block** in `load_llm_config()`:

```python
if provider == "gemini":
    return LLMConfig(
        provider="gemini",
        model=model or os.getenv("GEMINI_MODEL") or _default_model("gemini"),
        api_key=os.getenv("GEMINI_API_KEY"),
        base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
    )
```

**3. Add the env vars** to `.env.example`:

```
### Gemini
GEMINI_API_KEY=
GEMINI_BASE_URL=
GEMINI_MODEL=
```

**4. Update the auto-detection** logic if needed (the `provider == "auto"` block).

---

## Good First Issues

These are well-scoped tasks ideal for a first PR:

| Task | File | Complexity |
|------|------|------------|
| Add Gemini provider support | `llm_router.py` | Low |
| Add a Docker / docker-compose setup | repo root | Low–Medium |
| Windows compatibility testing and fixes | `tools/gui_ops.py`, `tools/system_ops.py` | Medium |
| Add a new tool module (e.g. calendar, clipboard, notifications) | `tools/` | Low |
| Improve error messages in browser_ops.py | `tools/browser_ops.py` | Low |
| Add a `--dry-run` flag to CLI | `cli.py` | Low |
| Write tests for `tools/file_ops.py` | `tools/` | Low–Medium |

If you're unsure where to start, open a Discussion and ask — happy to point you somewhere useful.

---

## Pull Request Guidelines

- **One PR per feature or fix** — keep it focused
- **Branch naming**: `feature/your-feature`, `fix/your-fix`, `docs/your-change`
- **Describe what and why** in the PR description — not just what the code does
- **Test your change** before submitting — run `python cli.py` and verify the tool or feature works end-to-end
- **Don't break existing tools** — quickly check that core tools (file ops, system ops) still work after your change
- PRs that add new tools should include a short example of the tool in action in the description

---

## Code Style

- Follow existing patterns in `tools/` — plain functions, `audit_log` calls, string return values
- Use type hints where practical
- No hard-coded API keys or secrets — always read from `os.getenv()`
- Keep imports minimal — don't add heavy dependencies without discussion

---

## Reporting Bugs

Open a GitHub Issue with:

1. What you were trying to do
2. The exact error message or unexpected behavior
3. Your OS, Python version, and which gateway you were using (CLI / Telegram / Discord)
4. Relevant lines from `agent_log.txt` if available

---

## Questions?

Open a GitHub Discussion or ping in the community chat. All contributions — code, docs, bug reports, ideas — are welcome.
