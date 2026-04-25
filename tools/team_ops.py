import json
from tools.database_ops import update_worker_status
from tools.base import audit_log

def report_completion(task_id: str, summary: str) -> str:
    """Worker tool: Report that the assigned task is complete."""
    update_worker_status(task_id, "completed", summary)
    audit_log("report_completion", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as completed."

def request_help(task_id: str, reason: str, context: str) -> str:
    """Worker tool: Report confusion and request Manager assistance."""
    details = json.dumps({"reason": reason, "context": context})
    update_worker_status(task_id, "needs_help", details)
    audit_log("request_help", {"task_id": task_id}, "success")
    return f"__WORKER_TERMINATE__: Task {task_id} marked as needs_help."
