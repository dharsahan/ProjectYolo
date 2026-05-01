from __future__ import annotations

import threading
import os
from typing import Any

from tools.base import audit_log, get_mem0_config
from tools.yolo_memory import TieredMemoryEngine

# Single, shared instance for the entire process
_memory_instance = None
_memory_lock = threading.Lock()

class NullMemory:
    def search(self, *_args: Any, **_kwargs: Any) -> list:
        return []

    def get_all(self, *_args: Any, **_kwargs: Any) -> list:
        return []

    def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def delete(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def delete_all(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def working_memory_set(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def working_memory_get(self, *_args: Any, **_kwargs: Any) -> dict:
        return {}

    def working_memory_clear(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def consolidate_memories(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def memory_stats(self, *_args: Any, **_kwargs: Any) -> dict:
        return {}

class HybridMemoryEngine:
    def __init__(self, mem0_engine, tiered_engine):
        self.mem0 = mem0_engine
        self.tiered = tiered_engine
        
    def __getattr__(self, name):
        # Default to tiered engine for specialized methods
        if hasattr(self.tiered, name):
            return getattr(self.tiered, name)
        return getattr(self.mem0, name)
        
    def add(self, fact, user_id=None, **kwargs):
        self.tiered.add(fact, user_id, **kwargs)
        try:
            self.mem0.add(fact, user_id=user_id, **kwargs)
        except Exception as e:
            audit_log("memory_hybrid_add", {}, "error", str(e))

def get_memory():
    """Get or create the shared global memory instance."""
    global _memory_instance
    if _memory_instance is not None:
        return _memory_instance

    with _memory_lock:
        if _memory_instance is not None:
            return _memory_instance

        try:
            use_mem0 = os.getenv("YOLO_MEMORY_ENGINE") == "mem0"
            use_hybrid = os.getenv("YOLO_MEM0_HYBRID", "false").lower() == "true"
            
            if use_mem0 and not use_hybrid:
                from mem0 import Memory
                config = get_mem0_config()
                _memory_instance = Memory.from_config(config)
            elif use_hybrid:
                from mem0 import Memory
                config = get_mem0_config()
                mem0_inst = Memory.from_config(config)
                tiered_inst = TieredMemoryEngine()
                _memory_instance = HybridMemoryEngine(mem0_inst, tiered_inst)
            else:
                _memory_instance = TieredMemoryEngine()
        except Exception as e:
            audit_log("memory_init", {}, "error", f"Falling back to NullMemory: {e}")
            _memory_instance = NullMemory()

    return _memory_instance
