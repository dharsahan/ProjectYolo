from tools.base import YOLO_SKILLS, audit_log


def self_upgrade_summary(
    user_id: int,
    feature_name: str,
    research_notes: str,
    implementation_notes: str,
    validation_notes: str,
) -> str:
    """Archive a structured self-upgrade summary as durable experience memory."""
    try:
        from tools.memory_service import get_memory

        memory = get_memory()
        summary = (
            f"SELF_UPGRADE: `{feature_name}`\n"
            f"RESEARCH: {research_notes}\n"
            f"IMPLEMENTATION: {implementation_notes}\n"
            f"VALIDATION: {validation_notes}"
        )
        memory.add(
            summary,
            user_id=str(user_id),
            metadata={"type": "self_upgrade", "feature": feature_name},
        )

        audit_log(
            "self_upgrade_summary",
            {"feature_name": feature_name, "user_id": user_id},
            "success",
        )
        return "Self-upgrade summary archived successfully."
    except Exception as e:
        audit_log("self_upgrade_summary", {"feature_name": feature_name}, "error", str(e))
        return f"Error archiving self-upgrade summary: {e}"

def optimize_skill(name: str, improvements: str) -> str:
    """Rewrite an existing skill manual with new improvements based on experience."""
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in {"_", "-"})
        if not safe_name:
            return "Error: Invalid skill name."

        skill_path = YOLO_SKILLS / f"{safe_name}.md"
        if not skill_path.exists():
            return f"Error: Skill '{name}' does not exist and cannot be optimized."

        # In a real scenario, Yolo would use its LLM power to merge the old and new.
        # Here we provide the tool to save the NEW optimized content.
        skill_path.write_text(improvements, encoding="utf-8")
        
        audit_log("optimize_skill", {"name": name}, "success")
        return f"Skill `{name}` has been autonomously optimized and updated."
    except Exception as e:
        audit_log("optimize_skill", {"name": name}, "error", str(e))
        return f"Error optimizing skill: {e}"

def archive_proactive_memory(user_id: int, insight: str) -> str:
    """Save an important technical insight immediately during a task."""
    try:
        from tools.memory_service import get_memory
        memory = get_memory()
        memory.add(f"INSIGHT: {insight}", user_id=str(user_id), metadata={"type": "proactive_insight"})
        
        audit_log("archive_proactive_memory", {"insight": insight[:50]}, "success")
        return "Insight successfully archived to long-term memory."
    except Exception as e:
        return f"Error archiving insight: {e}"
