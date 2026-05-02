from typing import Callable, Dict

TOOL_REGISTRY: Dict[str, Callable] = {}

def register_tool(name: str = None):
    """Decorator to register a function as an agent tool."""
    def decorator(func: Callable):
        tool_name = name or func.__name__
        TOOL_REGISTRY[tool_name] = func
        return func
    return decorator
