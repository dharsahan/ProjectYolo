import os
import json
import shlex
import asyncio
from contextlib import AsyncExitStack
from typing import Dict, Any, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools.base import YOLO_HOME, audit_log

MCP_CONFIG_PATH = YOLO_HOME / "mcp_servers.json"

class MCPManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.servers: Dict[str, dict] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tool_schemas: List[Dict[str, Any]] = []
        self._tool_to_server: Dict[str, str] = {}
        self._connections_initialized = False
        self._initialized = True

    def load_config(self):
        if not MCP_CONFIG_PATH.exists():
            with open(MCP_CONFIG_PATH, "w") as f:
                json.dump({"mcpServers": {}}, f, indent=4)
            return
        
        try:
            with open(MCP_CONFIG_PATH, "r") as f:
                data = json.load(f)
                self.servers = data.get("mcpServers", {})
        except Exception as e:
            audit_log("mcp_manager", {"path": str(MCP_CONFIG_PATH)}, "error", f"Failed to load config: {e}")

    async def initialize(self):
        """Connect to all configured servers and fetch tool schemas."""
        if self._connections_initialized:
            return
        self._connections_initialized = True
        self.load_config()
        self.tool_schemas = []
        self._tool_to_server = {}

        for server_name, server_info in self.servers.items():
            command = server_info.get("command")
            args = server_info.get("args", [])
            env = server_info.get("env", {})
            
            if not command:
                continue

            merged_env = os.environ.copy()
            merged_env.update(env)

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=merged_env
            )

            try:
                # Enter the stdio client context
                read_stream, write_stream = await self.exit_stack.enter_async_context(stdio_client(server_params))
                
                # Enter the session context
                session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
                
                await session.initialize()
                self.sessions[server_name] = session
                
                # Fetch tools
                tools = await session.list_tools()
                
                for t in tools.tools:
                    # Construct an OpenAI compatible schema
                    schema = {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": f"[MCP: {server_name}] {t.description or ''}",
                            "parameters": t.inputSchema or {"type": "object", "properties": {}}
                        }
                    }
                    self.tool_schemas.append(schema)
                    self._tool_to_server[t.name] = server_name
                    
                audit_log("mcp_manager", {"server": server_name}, "success", "Connected and loaded tools")
            except Exception as e:
                audit_log("mcp_manager", {"server": server_name}, "error", f"Failed to connect: {e}")

    async def cleanup(self):
        """Close all connections."""
        try:
            await self.exit_stack.aclose()
        except Exception:
            pass
        self.exit_stack = AsyncExitStack()
        self.sessions.clear()
        self.tool_schemas.clear()
        self._tool_to_server.clear()

    def get_server_for_tool(self, tool_name: str) -> str:
        return self._tool_to_server.get(tool_name)

    async def call_tool(self, tool_name: str, args: dict) -> str:
        server_name = self.get_server_for_tool(tool_name)
        if not server_name:
            raise ValueError(f"No MCP server found for tool: {tool_name}")
            
        session = self.sessions.get(server_name)
        if not session:
            raise ValueError(f"MCP server {server_name} is not connected")
            
        try:
            result = await session.call_tool(tool_name, args)
            
            # Normalize result
            if isinstance(result.content, str):
                return result.content
            if isinstance(result.content, list):
                normalized = []
                for item in result.content:
                    text = getattr(item, "text", None)
                    if text is not None:
                        normalized.append(str(text))
                    else:
                        normalized.append(str(item))
                return "\n".join(normalized)
            return str(result.content)
            
        except Exception as e:
            audit_log("mcp_manager_call", {"server": server_name, "tool": tool_name}, "error", str(e))
            return f"Error executing MCP tool {tool_name}: {e}"

# Global instance
mcp_manager = MCPManager()

from tools.registry import register_tool

@register_tool("list_mcp_servers")
async def list_mcp_servers() -> str:
    """Lists all configured MCP servers and their current connection status."""
    manager = mcp_manager
    await manager.initialize() # Ensure initialized
    
    if not manager.servers:
        return "No MCP servers configured."
    
    lines = ["Configured MCP Servers:"]
    for name, config in manager.servers.items():
        status = "Connected" if name in manager.sessions else "Disconnected/Error"
        tool_count = len([t for t, s in manager._tool_to_server.items() if s == name])
        lines.append(f"- {name}: {status} ({tool_count} tools)")
        lines.append(f"  Command: {config.get('command')} {' '.join(config.get('args', []))}")
    
    return "\n".join(lines)
