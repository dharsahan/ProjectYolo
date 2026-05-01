from tools.registry import register_tool
from tools.base import audit_log
from tools.memory_service import get_memory


@register_tool()
def memory_list(user_id: int) -> str:
    """List all stored memories for the current user using shared instance."""
    try:
        memory = get_memory()
        # mem0 v2.0.0 requires entity IDs in a filters dict
        results = memory.get_all(filters={"user_id": str(user_id)})

        if isinstance(results, dict) and "results" in results:
            results = results["results"]

        if not results:
            return "No memories found for your profile."

        output = "### Your Long-Term Memories:\n\n"
        for m in results:
            # Extremely resilient extraction
            if isinstance(m, dict):
                text = m.get("memory") or m.get("text") or str(m)
                mem_id = m.get("id") or m.get("memory_id") or "unknown"
            else:
                text = str(m)
                mem_id = "unknown"
            output += f"- `{mem_id}`: {text}\n"

        audit_log("memory_list", {"user_id": user_id}, "success")
        return output
    except Exception as e:
        audit_log("memory_list", {"user_id": user_id}, "error", str(e))
        return f"Error listing memories: {e}"


@register_tool()
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


@register_tool()
def memory_delete(memory_id: str) -> str:
    """Delete a single memory by its unique ID."""
    try:
        memory = get_memory()
        # OSS version uses memory_id as a positional or keyword argument
        memory.delete(memory_id=memory_id)
        audit_log("memory_delete", {"memory_id": memory_id}, "success")
        return f"Memory `{memory_id}` has been deleted."
    except Exception as e:
        audit_log("memory_delete", {"memory_id": memory_id}, "error", str(e))
        return f"Error deleting memory `{memory_id}`: {e}"


@register_tool()
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

# --- TieredMemoryEngine Working Memory Tools ---

from tools.yolo_memory import TieredMemoryEngine
from tools.memory_service import get_memory

_fallback_tiered_engine = None

def _get_working_memory_engine():
    engine = get_memory()
    if isinstance(engine, TieredMemoryEngine):
        return engine
    global _fallback_tiered_engine
    if _fallback_tiered_engine is None:
        _fallback_tiered_engine = TieredMemoryEngine()
    return _fallback_tiered_engine

@register_tool()
def working_memory_set(key: str, value: str, user_id: int = 0) -> str:
    """Write a scratchpad note for the current task."""
    try:
        _get_working_memory_engine().working_memory_set(user_id, key, value)
        audit_log("working_memory_set", {"user_id": user_id, "key": key}, "success")
        return f"Working memory set: {key} = {value}"
    except Exception as e:
        audit_log("working_memory_set", {"user_id": user_id, "key": key}, "error", str(e))
        return f"Error setting working memory: {e}"

@register_tool()
def working_memory_get(user_id: int = 0) -> str:
    """Read all working memory for the current task."""
    try:
        mem = _get_working_memory_engine().working_memory_get(user_id)
        audit_log("working_memory_get", {"user_id": user_id}, "success")
        if not mem:
            return "Working memory is empty."
        return "\n".join(f"{k}: {v}" for k, v in mem.items())
    except Exception as e:
        audit_log("working_memory_get", {"user_id": user_id}, "error", str(e))
        return f"Error getting working memory: {e}"

@register_tool()
def working_memory_clear(user_id: int = 0) -> str:
    """Wipe scratchpad after task completes."""
    try:
        _get_working_memory_engine().working_memory_clear(user_id)
        audit_log("working_memory_clear", {"user_id": user_id}, "success")
        return "Working memory cleared."
    except Exception as e:
        audit_log("working_memory_clear", {"user_id": user_id}, "error", str(e))
        return f"Error clearing working memory: {e}"

@register_tool()
def consolidate_memories(user_id: int = 0) -> str:
    """Manually trigger episodic to semantic promotion."""
    try:
        engine = _get_working_memory_engine()
        if hasattr(engine, "consolidate_memories"):
            engine.consolidate_memories(user_id)
            audit_log("consolidate_memories", {"user_id": user_id}, "success")
            return "Consolidation complete."
        return "Consolidation not supported by current memory engine."
    except Exception as e:
        audit_log("consolidate_memories", {"user_id": user_id}, "error", str(e))
        return f"Error consolidating memories: {e}"

@register_tool()
def memory_stats(user_id: int = 0) -> str:
    """Show tier counts, categories, last consolidation."""
    try:
        engine = _get_working_memory_engine()
        if hasattr(engine, "memory_stats"):
            stats = engine.memory_stats(user_id)
            audit_log("memory_stats", {"user_id": user_id}, "success")
            return "\n".join(f"{k}: {v}" for k, v in stats.items())
        return "Stats not supported by current memory engine."
    except Exception as e:
        audit_log("memory_stats", {"user_id": user_id}, "error", str(e))
        return f"Error getting memory stats: {e}"
