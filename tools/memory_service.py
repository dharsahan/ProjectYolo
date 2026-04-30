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
    def search(self, *_args: Any, **_kwargs: Any) -> dict:
        return {"results": []}

    def get_all(self, *_args: Any, **_kwargs: Any) -> list:
        return []

    def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def delete_all(self, *_args: Any, **_kwargs: Any) -> None:
        return None

def get_memory():
    """Get or create the shared global memory instance."""
    global _memory_instance
    if _memory_instance is not None:
        return _memory_instance

    with _memory_lock:
        if _memory_instance is not None:
            return _memory_instance

        try:
            if os.getenv("YOLO_MEMORY_ENGINE") == "mem0":
                from mem0 import Memory
                config = get_mem0_config()
                _memory_instance = Memory.from_config(config)
            else:
                _memory_instance = TieredMemoryEngine()
        except Exception as e:
            audit_log("memory_init", {}, "error", f"Falling back to NullMemory: {e}")
            _memory_instance = NullMemory()

    return _memory_instance
