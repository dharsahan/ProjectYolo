from tools.registry import register_tool
from tools.base import audit_log
from tools.memory_service import get_memory


@register_tool()
def learn_experience(user_id: int, task: str, error: str, resolution: str) -> str:
    """Record a technical error and how it was successfully resolved for future reference."""
    try:
        memory = get_memory()
        lesson = (
            f"EXPERIENCE: In task '{task}', encountered error: '{error}'. "
            f"RESOLVED BY: {resolution}. Avoid this in the future."
        )
        memory.add(
            lesson,
            user_id=str(user_id),
            metadata={"type": "experience", "status": "resolved"},
        )

        audit_log("learn_experience", {"task": task, "error": error}, "success")
        return (
            f"Technical lesson archived for future tasks: '{error}' -> '{resolution}'."
        )
    except Exception as e:
        audit_log("learn_experience", {"task": task}, "error", str(e))
        return f"Error archiving experience: {e}"


@register_tool()
def list_experiences(user_id: int) -> str:
    """Retrieve all technical engineering experiences/lessons learned."""
    try:
        memory = get_memory()
        # Search specifically for experience type
        # mem0 v2.0.0 requires entity IDs in a filters dict
        results = memory.get_all(filters={"user_id": str(user_id)})


        if isinstance(results, dict) and "results" in results:
            results = results["results"]

        experiences: list = []
        for m in results:
            is_exp = False
            if isinstance(m, dict):
                meta = m.get("metadata") or {}
                if meta.get("type") == "experience":
                    is_exp = True

            text = (
                m
                if isinstance(m, str)
                else (m.get("memory") or m.get("text") or str(m))
            )

            if is_exp or "EXPERIENCE:" in str(text):
                if text not in [e[2:] for e in experiences]:  # avoid exact duplicates
                    experiences.append(f"• {text}")

        if not experiences:
            return "No technical experiences recorded yet."

        audit_log("list_experiences", {"user_id": user_id}, "success")
        return "### Technical Lessons Learned:\n\n" + "\n".join(experiences)
    except Exception as e:
        return f"Error listing experiences: {e}"
