"""
MCP Tool Bridge - Dynamic tool discovery and routing for MCP servers.

This bridge connects to MCP servers, discovers their tools dynamically,
and converts them to formats compatible with various LLM providers.

Supports both transport types:
- STDIO: Local processes (spawns command)
- HTTP: Remote servers (Streamable HTTP transport)

When native LLM+MCP support arrives, this bridge can be replaced with
direct integration while keeping the same interface.
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import MCPServerConfig, MCPTransport

logger = logging.getLogger(__name__)


@dataclass
class BridgedTool:
    """A tool discovered from an MCP server, ready for LLM use."""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str
    _session: Optional[ClientSession] = None  # None for internal tools
    _internal_handler: Optional[Any] = None  # Callable for internal tools
    
    async def call(self, arguments: dict[str, Any]) -> Any:
        """Execute the tool via MCP or internal handler."""
        if self._internal_handler:
            # Internal tool - call the handler directly
            result = self._internal_handler(arguments)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        
        if not self._session:
            raise RuntimeError(f"Tool {self.name} has no session or handler")
            
        # MCP tool - call via session
        result = await self._session.call_tool(self.name, arguments)
        # Extract content from MCP result
        if hasattr(result, 'content') and result.content:
            contents = []
            for item in result.content:
                if hasattr(item, 'text'):
                    contents.append(item.text)
            return "\n".join(contents) if contents else str(result)
        return str(result)


@dataclass
class BridgedResource:
    """A resource discovered from an MCP server."""
    uri: str
    name: str
    description: str
    mime_type: str
    server_name: str


@dataclass
class ServerConnection:
    """Holds connection state for an MCP server."""
    config: MCPServerConfig
    session: ClientSession
    transport_type: MCPTransport
    exit_stack: AsyncExitStack  # Each server has its own exit stack for isolation
    resources: list[BridgedResource] = field(default_factory=list)


class MCPToolBridge:
    """
    Bridge between MCP servers and LLM tool interfaces.
    
    Uses AsyncExitStack to properly manage async context managers.
    
    Usage:
        async with MCPToolBridge() as bridge:
            await bridge.connect([server_config1, server_config2])
            tools = bridge.to_anthropic_tools()
            result = await bridge.call_tool("search_people", {"name": "John"})
    """
    
    def __init__(self):
        self._tools: dict[str, BridgedTool] = {}
        self._connections: dict[str, ServerConnection] = {}
        self._exit_stack: Optional[AsyncExitStack] = None
        self._connected = False
    
    async def __aenter__(self) -> "MCPToolBridge":
        """Enter async context - initializes the exit stack."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - cleans up all connections individually."""
        # Clean up each server's exit stack separately to prevent cascade failures
        for name, conn in list(self._connections.items()):
            try:
                await conn.exit_stack.__aexit__(None, None, None)
                logger.debug(f"Disconnected from {name}")
            except Exception as e:
                logger.warning(f"Error disconnecting from {name}: {e}")
        
        self._connections.clear()
        self._tools.clear()
        self._connected = False
    
    @property
    def tools(self) -> dict[str, BridgedTool]:
        """All discovered tools, keyed by name."""
        return self._tools
    
    @property
    def tool_names(self) -> list[str]:
        """List of all available tool names."""
        return list(self._tools.keys())
    
    def register_internal_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Any  # Callable that takes arguments dict
    ) -> None:
        """
        Register an internal tool (not from MCP server).
        
        Used for agent-internal tools like expand_reference.
        
        Args:
            name: Tool name
            description: Tool description for LLM
            input_schema: JSON Schema for tool parameters
            handler: Callable(arguments: dict) -> result
        """
        tool = BridgedTool(
            name=name,
            description=description,
            input_schema=input_schema,
            server_name="_internal",
            _session=None,
            _internal_handler=handler
        )
        self._tools[name] = tool
        logger.info(f"Registered internal tool: {name}")
    
    def is_connected(self) -> bool:
        """Check if bridge is connected to MCP servers."""
        return self._connected
    
    async def connect(self, servers: list[MCPServerConfig]) -> None:
        """
        Connect to MCP servers and discover their tools.
        
        Args:
            servers: List of MCP server configurations to connect to
        """
        if not self._exit_stack:
            raise RuntimeError("MCPToolBridge must be used as async context manager")
        
        for server_config in servers:
            if not server_config.enabled:
                logger.info(f"Skipping disabled server: {server_config.name}")
                continue
                
            try:
                await self._connect_server(server_config)
                logger.info(f"Connected to {server_config.name} ({server_config.transport.value})")
            except Exception as e:
                logger.error(f"Failed to connect to {server_config.name}: {e}")
        
        self._connected = True
        logger.info(f"Bridge connected. {len(self._tools)} tools available.")
    
    async def _connect_server(self, config: MCPServerConfig) -> None:
        """Connect to a single MCP server and discover its tools."""
        if config.transport == MCPTransport.STDIO:
            await self._connect_stdio(config)
        elif config.transport in (MCPTransport.HTTP, MCPTransport.STREAMABLE_HTTP):
            await self._connect_http(config)
        else:
            raise ValueError(f"Unknown transport type: {config.transport}")
    
    async def _connect_stdio(self, config: MCPServerConfig) -> None:
        """Connect to a STDIO (local process) MCP server."""
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env={**dict(config.env)} if config.env else None
        )
        
        # Each server gets its own exit stack for isolation
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()
        
        try:
            read_stream, write_stream = await server_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            # Create and initialize session
            session = await server_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            
            # Store connection with its exit stack
            self._connections[config.name] = ServerConnection(
                config=config,
                session=session,
                transport_type=MCPTransport.STDIO,
                exit_stack=server_stack
            )
            
            # Discover tools
            await self._discover_tools(config.name, session)
        except Exception:
            # Clean up this server's stack on failure
            await server_stack.__aexit__(None, None, None)
            raise
    
    async def _connect_http(self, config: MCPServerConfig) -> None:
        """Connect to an HTTP MCP server using Streamable HTTP transport."""
        import httpx
        from mcp.client.streamable_http import streamablehttp_client
        
        # Pre-check: verify server is reachable before entering context
        # Use a simple GET or OPTIONS to check connectivity (not a full MCP request)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try OPTIONS first (lightweight), fall back to POST with empty body
                try:
                    response = await client.options(config.url)
                except httpx.HTTPStatusError:
                    # Some servers may not support OPTIONS, try a basic POST
                    response = await client.post(
                        config.url,
                        content=b"",
                        headers={"Content-Type": "application/json"}
                    )
                # Any response (even 4xx/5xx) means server is up
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout) as e:
            raise ConnectionError(f"Server {config.name} not reachable at {config.url}: {e}")
        
        # Each server gets its own exit stack for isolation
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()
        
        try:
            # Pass user-specific headers (e.g. per-user auth tokens from CredentialStore)
            client_kwargs = {"url": config.url}
            if config.headers:
                client_kwargs["headers"] = dict(config.headers)
            streams = await server_stack.enter_async_context(
                streamablehttp_client(**client_kwargs)
            )
            read_stream, write_stream = streams[0], streams[1]
            
            # Create and initialize session
            session = await server_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            
            # Store connection with its exit stack
            self._connections[config.name] = ServerConnection(
                config=config,
                session=session,
                transport_type=MCPTransport.HTTP,
                exit_stack=server_stack
            )
            
            # Discover tools and resources
            await self._discover_tools(config.name, session)
            await self._discover_resources(config.name, session)
        except Exception:
            # Clean up this server's stack on failure
            try:
                await server_stack.__aexit__(None, None, None)
            except Exception:
                pass  # Suppress cleanup errors
            raise
    
    async def _discover_tools(self, server_name: str, session: ClientSession) -> None:
        """Discover and register tools from a connected server."""
        tools_result = await session.list_tools()
        
        for mcp_tool in tools_result.tools:
            tool = BridgedTool(
                name=mcp_tool.name,
                description=mcp_tool.description or "",
                input_schema=mcp_tool.inputSchema if hasattr(mcp_tool, 'inputSchema') else {},
                server_name=server_name,
                _session=session
            )
            
            # Handle name collisions with server prefix
            if mcp_tool.name in self._tools:
                prefixed_name = f"{server_name}_{mcp_tool.name}"
                logger.warning(f"Tool name collision: {mcp_tool.name}. Using {prefixed_name}")
                self._tools[prefixed_name] = tool
            else:
                self._tools[mcp_tool.name] = tool
        
        logger.debug(f"Discovered {len(tools_result.tools)} tools from {server_name}")
    
    async def _discover_resources(self, server_name: str, session: ClientSession) -> None:
        """Discover resources from a connected server."""
        try:
            resources_result = await session.list_resources()
            
            connection = self._connections.get(server_name)
            if connection:
                for mcp_resource in resources_result.resources:
                    resource = BridgedResource(
                        uri=str(mcp_resource.uri) if hasattr(mcp_resource, 'uri') else "",
                        name=mcp_resource.name if hasattr(mcp_resource, 'name') else "",
                        description=mcp_resource.description if hasattr(mcp_resource, 'description') else "",
                        mime_type=mcp_resource.mimeType if hasattr(mcp_resource, 'mimeType') else "",
                        server_name=server_name
                    )
                    connection.resources.append(resource)
                
                logger.debug(f"Discovered {len(resources_result.resources)} resources from {server_name}")
        except Exception as e:
            # Resources are optional, log but don't fail
            logger.debug(f"No resources from {server_name} (or error: {e})")
    
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """
        Execute a tool by name.
        
        Args:
            name: The tool name
            arguments: Tool arguments as a dictionary
            
        Returns:
            Tool execution result
            
        Raises:
            KeyError: If tool not found
        """
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}. Available: {self.tool_names}")
        
        tool = self._tools[name]
        logger.debug(f"Calling tool {name} on server {tool.server_name}")
        return await tool.call(arguments)
    
    # ==================== LLM Format Conversions ====================
    
    def to_anthropic_tools(self) -> list[dict[str, Any]]:
        """Convert tools to Anthropic/Claude API format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in self._tools.values()
        ]
    
    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Convert tools to OpenAI API format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }
            for tool in self._tools.values()
        ]
    
    def to_ollama_tools(self) -> list[dict[str, Any]]:
        """Convert tools to Ollama format (same as OpenAI)."""
        return self.to_openai_tools()

    def to_filtered_tools(
        self,
        allowed_servers: Optional[list[str]],
        provider: str = "claude",
    ) -> list[dict[str, Any]]:
        """
        Return tools filtered to the given server names.

        Args:
            allowed_servers: List of server names to include, or None for all tools.
            provider: "claude" (Anthropic format) or "openai"/"ollama" (OpenAI format).

        The "_internal" server (expand_reference) is always included.
        """
        if allowed_servers is None:
            # Unrestricted — return all tools in the right format
            if provider == "claude":
                return self.to_anthropic_tools()
            return self.to_openai_tools()

        allowed_set = set(allowed_servers) | {"_internal"}

        if provider == "claude":
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in self._tools.values()
                if tool.server_name in allowed_set
            ]
        else:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in self._tools.values()
                if tool.server_name in allowed_set
            ]
    
    def get_tools_summary(self) -> str:
        """Get a human-readable summary of available tools."""
        by_server: dict[str, list[str]] = {}
        server_transports: dict[str, str] = {}
        
        for tool in self._tools.values():
            if tool.server_name not in by_server:
                by_server[tool.server_name] = []
                if tool.server_name in self._connections:
                    server_transports[tool.server_name] = self._connections[tool.server_name].transport_type.value
                else:
                    server_transports[tool.server_name] = "unknown"
            by_server[tool.server_name].append(f"  - {tool.name}: {tool.description[:60]}...")
        
        lines = ["Available MCP Tools:"]
        for server, tools in by_server.items():
            transport = server_transports.get(server, "?")
            lines.append(f"\n[{server}] ({transport})")
            lines.extend(tools)
        
        return "\n".join(lines)
