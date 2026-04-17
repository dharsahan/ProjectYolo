from tools.artifact_ops import create_artifact, get_latest_artifact, list_artifacts
from tools.background_ops import (dispatch_parallel_agents,
                                  run_background_mission)
from tools.browser_ops import (browser_click, browser_click_at, browser_close,
                                browser_crawl_step,
                                browser_click_next,
                                browser_extract_text, browser_navigate,
                                browser_extract_links,
                                browser_press_key, browser_screenshot,
                                browser_scroll,
                                browser_scroll_until_end,
                                browser_type, browser_wait)
from tools.cron_ops import (cancel_scheduled_task, get_scheduled_tasks,
                            schedule_daily_task, schedule_task)
from tools.evolution_ops import (archive_proactive_memory, optimize_skill,
                                 self_upgrade_summary)
from tools.experience_ops import learn_experience, list_experiences
from tools.file_ops import (copy_file, delete_file, edit_file, file_info,
                            list_dir, make_dir, move_file, read_file,
                            search_in_file, send_to_telegram, write_file)
from tools.identity_ops import read_user_identity, update_user_identity
from tools.mcp_ops import mcp_list_tools, mcp_run_tool
from tools.memory_ops import memory_add, memory_delete, memory_list, memory_wipe
from tools.mission_ops import create_mission, read_mission, update_mission
from tools.research_ops import (research_clear, research_get_all_summaries,
                                research_enqueue_from_crawl_step,
                                research_get_next, research_queue_urls,
                                research_store_summary)
from tools.skill_ops import develop_new_skill, list_skills, read_skill
from tools.system_ops import run_bash
from tools.web_ops import browse_url, web_search
from tools.gui_ops import (gui_mouse_move, gui_mouse_click, gui_type_text, 
                           gui_press_key, gui_screenshot, gui_get_screen_size)

__all__ = [
    "TOOLS_SCHEMAS",
    "copy_file",
    "delete_file",
    "edit_file",
    "file_info",
    "list_dir",
    "make_dir",
    "move_file",
    "read_file",
    "search_in_file",
    "write_file",
    "send_to_telegram",
    "list_skills",
    "read_skill",
    "develop_new_skill",
    "run_bash",
    "create_mission",
    "read_mission",
    "update_mission",
    "create_artifact",
    "list_artifacts",
    "get_latest_artifact",
    "web_search",
    "browse_url",
    "browser_navigate",
    "browser_click",
    "browser_click_at",
    "browser_press_key",
    "browser_scroll",
    "browser_scroll_until_end",
    "browser_crawl_step",
    "browser_type",
    "browser_extract_links",
    "browser_click_next",
    "browser_screenshot",
    "browser_extract_text",
    "browser_wait",
    "browser_close",
    "research_queue_urls",
    "research_enqueue_from_crawl_step",
    "research_get_next",
    "research_store_summary",
    "research_get_all_summaries",
    "research_clear",
    "memory_list",
    "memory_wipe",
    "memory_add",
    "memory_delete",
    "mcp_list_tools",
    "mcp_run_tool",
    "learn_experience",
    "list_experiences",
    "run_background_mission",
    "dispatch_parallel_agents",
    "schedule_task",
    "schedule_daily_task",
    "get_scheduled_tasks",
    "cancel_scheduled_task",
    "optimize_skill",
    "archive_proactive_memory",
    "self_upgrade_summary",
    "read_user_identity",
    "update_user_identity",
    "gui_mouse_move",
    "gui_mouse_click",
    "gui_type_text",
    "gui_press_key",
    "gui_screenshot",
    "gui_get_screen_size",
]

# Define all schemas in one place for the agent
TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "update_user_identity",
            "description": "Refine the structural Markdown document that defines the user's engineering style, project preferences, and unstated goals. Use this to ensure I adapt to the user's specific way of working.",
            "parameters": {
                "type": "object",
                "properties": {
                    "observations": {
                        "type": "string",
                        "description": "The full updated Markdown content of the identity file.",
                    }
                },
                "required": ["observations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_user_identity",
            "description": "Read the Master User Identity profile to understand how to best tailor my reasoning and code to the user's specific style.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_skill",
            "description": "Rewrite an existing skill manual with new improvements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "improvements": {"type": "string"}
                },
                "required": ["name", "improvements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "archive_proactive_memory",
            "description": "Save a critical technical insight immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "insight": {"type": "string"}
                },
                "required": ["insight"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "self_upgrade_summary",
            "description": "Archive a structured summary of a self-upgrade (research, implementation, validation).",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_name": {"type": "string"},
                    "research_notes": {"type": "string"},
                    "implementation_notes": {"type": "string"},
                    "validation_notes": {"type": "string"}
                },
                "required": [
                    "feature_name",
                    "research_notes",
                    "implementation_notes",
                    "validation_notes"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": "Schedule a recurring autonomous task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string"},
                    "interval_minutes": {"type": "integer"}
                },
                "required": ["task_description", "interval_minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_daily_task",
            "description": "Schedule a recurring autonomous task that runs every day.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string"}
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_scheduled_tasks",
            "description": "List all active recurring tasks.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_task",
            "description": "Stop and delete a recurring task by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron_id": {"type": "integer"}
                },
                "required": ["cron_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_parallel_agents",
            "description": "Spawn multiple specialized agents in parallel to handle distinct sub-tasks and wait for their combined results. Use this for complex multi-faceted research or batch processing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objectives": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of specific instructions for each agent."
                    }
                },
                "required": ["objectives"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_background_mission",
            "description": "Execute a highly complex task in the background.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"}
                },
                "required": ["objective"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "learn_experience",
            "description": "Record a technical lesson or bug fix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "error": {"type": "string"},
                    "resolution": {"type": "string"}
                },
                "required": ["task", "error", "resolution"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiences",
            "description": "List all technical lessons learned.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_list_tools",
            "description": "List tools on an MCP server.",
            "parameters": {
                "type": "object",
                "properties": {"server_command": {"type": "string"}},
                "required": ["server_command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_run_tool",
            "description": "Run an MCP tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_command": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "tool_args": {"type": "object"}
                },
                "required": ["server_command", "tool_name", "tool_args"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_add",
            "description": "Remember a user fact.",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete a single specific memory by its unique ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The unique UUID of the memory to delete."
                    }
                },
                "required": ["memory_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "Show long-term memories.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_wipe",
            "description": "Delete user memories.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_queue_urls",
            "description": "Add URLs to persistent queue.",
            "parameters": {
                "type": "object",
                "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
                "required": ["urls"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_enqueue_from_crawl_step",
            "description": "Parse `browser_crawl_step` output, filter low-signal links, and enqueue high-quality URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "crawl_step_output": {"type": "string"},
                    "topic_hint": {"type": "string"},
                    "max_urls": {"type": "integer"}
                },
                "required": ["crawl_step_output"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_get_next",
            "description": "Get next URL from queue.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_store_summary",
            "description": "Store a site summary to disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "summary": {"type": "string"}
                },
                "required": ["url", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_get_all_summaries",
            "description": "Retrieve all source summaries.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_clear",
            "description": "Delete research state.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate live browser.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click web element.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click_at",
            "description": "Click (x, y) coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a keyboard key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll page in multiple steps to load deeper content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["down", "up"]},
                    "pixels": {"type": "integer"},
                    "steps": {"type": "integer"},
                    "delay_seconds": {"type": "number"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll_until_end",
            "description": "Auto-scroll until page height stops growing on infinite-scroll pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_rounds": {"type": "integer"},
                    "step_pixels": {"type": "integer"},
                    "settle_delay_seconds": {"type": "number"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_crawl_step",
            "description": "Run one crawl step: scroll to load content, extract links, optionally click next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "link_limit": {"type": "integer"},
                    "same_domain": {"type": "boolean"},
                    "try_next": {"type": "boolean"},
                    "max_scroll_rounds": {"type": "integer"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract_links",
            "description": "Extract normalized links from current page for deep crawl/pagination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "same_domain": {"type": "boolean"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click_next",
            "description": "Click a next/load-more control to go beyond the first page.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type into input field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                    "press_enter": {"type": "boolean"}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Screenshot current page.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract_text",
            "description": "Extract visible text.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "Pause browser execution.",
            "parameters": {
                "type": "object",
                "properties": {"seconds": {"type": "number"}},
                "required": ["seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close browser session.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_url",
            "description": "Fetch URL text content.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "develop_new_skill",
            "description": "Record skill manual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_to_telegram",
            "description": "Upload file to user.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_artifact",
            "description": "Generate persistent deliverable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "file_type": {"type": "string"}
                },
                "required": ["name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_artifacts",
            "description": "List artifacts.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_artifact",
            "description": "Upload the newest artifact file.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_mission",
            "description": "Initialize mission plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"},
                    "strategy": {"type": "string"}
                },
                "required": ["objective", "strategy"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_mission",
            "description": "Record mission progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "step_description": {"type": "string"}
                },
                "required": ["step_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_mission",
            "description": "Read mission status.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List available skills.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Read skill manual.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace text in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dest": {"type": "string"}
                },
                "required": ["src", "dest"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dest": {"type": "string"}
                },
                "required": ["src", "dest"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "make_dir",
            "description": "Create a new directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "Get metadata.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compact_conversation",
            "description": "Summarize the current conversation history to save context space while preserving key technical details and mission progress.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_file",
            "description": "Search regex in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"}
                },
                "required": ["path", "pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_mouse_move",
            "description": "Move the mouse cursor to a specific (x, y) coordinate. Use carefully on GUI interfaces.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number", "description": "Duration of the movement in seconds"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_mouse_click",
            "description": "Click a mouse button.",
            "parameters": {
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer", "description": "Number of clicks"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_type_text",
            "description": "Type a string of characters using the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval": {"type": "number", "description": "Seconds between each key press"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_press_key",
            "description": "Press a single key or a hotkey combination (e.g., 'enter', 'ctrl+c').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_screenshot",
            "description": "Take a screenshot and save it to the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gui_get_screen_size",
            "description": "Get the screen resolution.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]
