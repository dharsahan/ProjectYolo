from tools.registry import register_tool
from pathlib import Path

from tools.base import YOLO_SKILLS, audit_log


@register_tool()
def list_skills() -> str:
    """List all available specialized skills in the global skills directory."""
    try:
        skills_dir = YOLO_SKILLS
        if not skills_dir.exists():
            return "No skills directory found."

        skills = []
        for file in skills_dir.glob("*.md"):
            skills.append(f"• {file.stem}")

        audit_log("list_skills", {}, "success")
        return "Available Specialized Skills:\n" + (
            "\n".join(skills) if skills else "No skills defined yet."
        )
    except Exception as e:
        audit_log("list_skills", {}, "error", str(e))
        return f"Error listing skills: {e}"


@register_tool()
def read_skill(name: str) -> str:
    """Read the full manual/procedure for a specific skill."""
    try:
        safe_name = Path(name).name
        if safe_name != name:
            return "Error: Invalid skill name."

        if safe_name.endswith(".md"):
            safe_name = safe_name[:-3]

        skill_path = YOLO_SKILLS / f"{safe_name}.md"
        if not skill_path.exists():
            return f"Error: Skill '{name}' not found."

        content = skill_path.read_text(encoding="utf-8")
        audit_log("read_skill", {"name": name}, "success")
        return f"### Skill: {name}\n\n{content}"
    except Exception as e:
        audit_log("read_skill", {"name": name}, "error", str(e))
        return f"Error reading skill: {e}"


@register_tool()
def develop_new_skill(name: str, content: str) -> str:
    """Autonomously develop and record a new specialized skill in the skills directory."""
    try:
        skills_dir = YOLO_SKILLS
        skills_dir.mkdir(exist_ok=True)

        # Sanitize name
        safe_name = name.lower().replace(" ", "_")
        safe_name = "".join(
            c for c in safe_name if c.isalnum() or c in {"_", "-", "."}
        ).strip("._")
        if not safe_name:
            return "Error: Invalid skill name."

        if not safe_name.endswith(".md"):
            filename = f"{safe_name}.md"
        else:
            filename = safe_name

        file_path = skills_dir / filename

        # Format content as a professional manual if not already
        if not content.startswith("# Skill:"):
            content = f"# Skill: {name.title()}\n\n{content}"

        file_path.write_text(content, encoding="utf-8")

        audit_log("develop_new_skill", {"name": name}, "success")
        return f"New skill successfully developed and recorded: `{name}`. I can now reference this manual in future tasks."
    except Exception as e:
        audit_log("develop_new_skill", {"name": name}, "error", str(e))
        return f"Error developing new skill: {e}"
