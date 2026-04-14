from tools.base import audit_log
from tools.memory_service import get_memory

def memory_list(user_id: int) -> str:
    """List all stored memories for the current user using shared instance."""
    try:
        memory = get_memory()
        results = memory.get_all(user_id=str(user_id))
        
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        
        if not results:
            return "No memories found for your profile."
            
        output = "### Your Long-Term Memories:\n\n"
        for i, m in enumerate(results, 1):
            # Extremely resilient text extraction
            if isinstance(m, dict):
                text = m.get('memory') or m.get('text') or str(m)
            else:
                text = str(m)
            output += f"{i}. {text}\n"
            
        audit_log("memory_list", {"user_id": user_id}, "success")
        return output
    except Exception as e:
        audit_log("memory_list", {"user_id": user_id}, "error", str(e))
        return f"Error listing memories: {e}"

def memory_add(user_id: int, fact: str) -> str:
    """Manually add a specific fact using shared instance."""
    try:
        memory = get_memory()
        memory.add(fact, user_id=str(user_id))
        audit_log("memory_add", {"user_id": user_id, "fact": fact}, "success")
        return f"Fact successfully remembered: `{fact}`"
    except Exception as e:
        audit_log("memory_add", {"user_id": user_id, "fact": fact}, "error", str(e))
        return f"Error adding memory: {e}"

def memory_wipe(user_id: int) -> str:
    """Permanently delete all memories using shared instance."""
    try:
        memory = get_memory()
        memory.delete_all(user_id=str(user_id))
        audit_log("memory_wipe", {"user_id": user_id}, "success")
        return "All your memories have been permanently deleted."
    except Exception as e:
        audit_log("memory_wipe", {"user_id": user_id}, "error", str(e))
        return f"Error wiping memories: {e}"
