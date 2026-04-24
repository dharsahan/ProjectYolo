"""
Plugin Manager for Project Yolo.

Dynamically loads external tools from the `plugins/` directory.
A plugin is just a Python file containing:
1. `PLUGIN_SCHEMAS`: A list of OpenAI function schema dictionaries.
2. The corresponding handler functions matching the schema names.
"""

import importlib.util
import inspect
from pathlib import Path
from typing import Dict, List, Callable, Any

from tools.base import YOLO_HOME, audit_log

# Plugins are stored globally in the Yolo config directory
PLUGIN_DIR = YOLO_HOME / "plugins"


def load_plugins() -> tuple[List[Dict[str, Any]], Dict[str, Callable]]:
    """
    Scans the plugins/ directory and loads dynamic tools.
    Returns:
        schemas: A list of OpenAI-compatible function schemas.
        handlers: A dictionary mapping function names to callables.
    """
    schemas: list = []
    handlers: dict = {}

    if not PLUGIN_DIR.exists():
        try:
            PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            return schemas, handlers

    for file in PLUGIN_DIR.glob("*.py"):
        if file.name.startswith("__"):
            continue

        module_name = f"plugins.{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(file))
        if not spec or not spec.loader:
            continue

        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Extract schemas
            if hasattr(module, "PLUGIN_SCHEMAS") and isinstance(
                module.PLUGIN_SCHEMAS, list
            ):
                schemas.extend(module.PLUGIN_SCHEMAS)

            # Extract handlers
            if hasattr(module, "PLUGIN_HANDLERS") and isinstance(
                module.PLUGIN_HANDLERS, dict
            ):
                handlers.update(module.PLUGIN_HANDLERS)
            else:
                # Auto-discover functions matching the schema names
                if hasattr(module, "PLUGIN_SCHEMAS"):
                    for schema in module.PLUGIN_SCHEMAS:
                        func_name = schema.get("function", {}).get("name")
                        if func_name and hasattr(module, func_name):
                            func = getattr(module, func_name)
                            if inspect.isfunction(func) or inspect.iscoroutinefunction(
                                func
                            ):
                                handlers[func_name] = func

            audit_log("plugin_loaded", {"plugin": file.name}, "success")
        except Exception as e:
            audit_log("plugin_failed", {"plugin": file.name}, "error", str(e))
            print(f"[PluginManager] Failed to load plugin {file.name}: {e}")

    return schemas, handlers


# Cache the loaded plugins at startup
PLUGIN_SCHEMAS, PLUGIN_HANDLERS = load_plugins()
