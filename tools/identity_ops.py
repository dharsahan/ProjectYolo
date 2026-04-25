from tools.base import YOLO_HOME, audit_log

IDENTITY_FILE = YOLO_HOME / "identity.md"


def read_user_identity() -> str:
    """Read the current Master User Identity profile."""
    try:
        if not IDENTITY_FILE.exists():
            return "No User Identity profile found yet. I am still learning your style."
        return IDENTITY_FILE.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading identity: {e}"


def update_user_identity(observations: str) -> str:
    """Refine the Master User Identity with new technical or psychological observations."""
    try:
        # In a real turn, Yolo (the LLM) provides the FULL updated Markdown.
        # This tool simply saves the high-fidelity reflection.
        IDENTITY_FILE.write_text(observations, encoding="utf-8")

        audit_log("update_user_identity", {"len": len(observations)}, "success")
        return "Master User Identity has been updated and synchronized with my current understanding of you."
    except Exception as e:
        audit_log("update_user_identity", {}, "error", str(e))
        return f"Error updating identity: {e}"
