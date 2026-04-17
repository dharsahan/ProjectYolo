import json
from pathlib import Path
from typing import Optional
from tools.base import YOLO_MISSION_FILE, audit_log

MISSION_FILE = YOLO_MISSION_FILE

def create_mission(objective: str, strategy: str) -> str:
    """Initialize a new mission plan for a complex task."""
    try:
        mission_data = {
            "objective": objective,
            "strategy": strategy,
            "current_step": 0,
            "steps_completed": [],
            "status": "in_progress"
        }
        Path(MISSION_FILE).write_text(json.dumps(mission_data, indent=2), encoding="utf-8")
        audit_log("create_mission", {"objective": objective}, "success")
        return f"Mission initialized: {objective}. Strategy recorded in `{MISSION_FILE}`."
    except Exception as e:
        audit_log("create_mission", {"objective": objective}, "error", str(e))
        return f"Error creating mission: {e}"

def update_mission(step_description: str, status: str = "completed") -> str:
    """Record progress on the current mission."""
    try:
        path = Path(MISSION_FILE)
        if not path.exists():
            return "Error: No active mission found. Use `create_mission` first."
        
        mission_data = json.loads(path.read_text(encoding="utf-8"))
        mission_data["current_step"] += 1
        mission_data["steps_completed"].append({
            "step": mission_data["current_step"],
            "description": step_description,
            "status": status
        })
        
        path.write_text(json.dumps(mission_data, indent=2), encoding="utf-8")
        audit_log("update_mission", {"step": step_description}, "success")
        return f"Mission updated: Step {mission_data['current_step']} marked as {status}."
    except Exception as e:
        audit_log("update_mission", {}, "error", str(e))
        return f"Error updating mission: {e}"

def read_mission() -> str:
    """Retrieve the current mission status and strategy."""
    try:
        path = Path(MISSION_FILE)
        if not path.exists():
            return "No active mission. I am currently in idle mode."
        
        mission_data = json.loads(path.read_text(encoding="utf-8"))
        summary = (
            f"### Active Mission: {mission_data['objective']}\n"
            f"**Strategy**: {mission_data['strategy']}\n"
            f"**Progress**: {len(mission_data['steps_completed'])} steps completed.\n"
        )
        if mission_data['steps_completed']:
            summary += "**Last Action**: " + mission_data['steps_completed'][-1]['description']
            
        audit_log("read_mission", {}, "success")
        return summary
    except Exception as e:
        audit_log("read_mission", {}, "error", str(e))
        return f"Error reading mission: {e}"
