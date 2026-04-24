import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# Global Yolo Paths
YOLO_HOME = (
    Path(os.getenv("YOLO_HOME", str(Path.home() / ".yolo"))).expanduser().resolve()
)
YOLO_SKILLS = YOLO_HOME / "skills"
YOLO_BROWSER_PROFILE = YOLO_HOME / "browser_profile"
YOLO_MISSION_FILE = YOLO_HOME / ".yolo_mission"
YOLO_RESEARCH_FILE = YOLO_HOME / ".yolo_research_state"
YOLO_LOG_FILE = YOLO_HOME / "agent_log.txt"

# Local Paths (for deliverables)
YOLO_ARTIFACTS = Path(os.getenv("YOLO_ARTIFACTS_DIR", "artifacts")).expanduser()

# Ensure core system directories exist
for directory in [YOLO_HOME, YOLO_SKILLS, YOLO_BROWSER_PROFILE, YOLO_ARTIFACTS]:
    directory.mkdir(parents=True, exist_ok=True)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_and_verify_path(
    target_path: Union[str, Path], confirm_func: Optional[Callable] = None
) -> Path:
    """
    Resolve path and verify it stays within the current working directory.
    If outside, ask for permission via confirm_func.
    Always rejects sensitive OS prefixes.
    """
    raw_path = str(target_path)
    if "\x00" in raw_path:
        raise ValueError("Invalid path: null byte detected")

    cwd = Path.cwd().resolve()
    try:
        # Resolve path without requiring it to exist
        resolved = Path(raw_path).expanduser().resolve(strict=False)
    except Exception as e:
        raise ValueError(f"Invalid path: {e}") from e

    # Sensitive OS Prefixes (Hard Block)
    if os.name == "nt":
        sensitive_prefixes = [
            Path("C:/Windows"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            Path("C:/Users/Public"),
            Path("C:/Windows/System32"),
        ]
    else:
        sensitive_prefixes = [
            Path("/etc"),
            Path("/sys"),
            Path("/proc"),
            Path("/var"),
            Path("/root"),
            Path("/boot"),
            Path("/dev"),
        ]

    for prefix in sensitive_prefixes:
        try:
            if resolved == prefix or _is_relative_to(resolved, prefix):
                raise PermissionError(
                    f"CRITICAL ACCESS DENIED: Path '{target_path}' is a sensitive system directory and is permanently blocked for security."
                )
        except Exception:
            # Handle cases where path comparison might fail due to drive mismatches or other OS quirks
            continue

    # CWD Sandboxing (Soft Block with Confirmation)
    if not _is_relative_to(resolved, cwd):
        if confirm_func and confirm_func("access out-of-scope path", str(resolved)):
            return resolved
        raise PermissionError(
            f"Access denied: Path '{target_path}' is outside the allowed workspace. "
            "Permission was not granted to exit the sandbox."
        )

    return resolved


def audit_log(tool: str, args: Dict[str, Any], status: str, detail: str = ""):
    """Append a structured log entry to the global agent_log.txt."""
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "tool": tool,
        "args": args,
        "status": status,
        "detail": detail,
    }
    try:
        with open(YOLO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass


def get_mem0_config():
    """Returns the standardized configuration for Mem0."""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("MODEL_NAME", "gpt-4o")
    memory_path = YOLO_HOME / "memory"
    memory_path.mkdir(exist_ok=True)

    return {
        "llm": {
            "provider": "openai",
            "config": {"api_key": api_key, "openai_base_url": base_url, "model": model},
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": api_key,
                "openai_base_url": base_url,
                "model": "text-embedding-3-small",
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": str(memory_path / "qdrant"),
            },
        },
        "history_db_path": str(memory_path / "history.db"),
    }
