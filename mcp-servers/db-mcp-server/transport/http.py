"""
Streamable HTTP transport for MCP (Model Context Protocol).

Implements the official MCP Streamable HTTP specification:
- Single /mcp endpoint for all JSON-RPC communication
- POST /mcp: accepts JSON-RPC requests, responds with JSON or SSE
- GET /mcp: optional persistent SSE stream for server notifications
- /healthz: health check endpoint (separate from /mcp)

This module imports and reuses all handler functions from the main server.py,
avoiding code duplication while providing HTTP transport.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_202_ACCEPTED, HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
import uvicorn

from database import DatabaseConnection
from config import DatabaseConfig
from container import RepositoryContainer

# Import utility functions
from utils.sse import format_sse_event, format_sse_error
from utils.jsonrpc import (
    is_valid_jsonrpc, is_notification,
    create_success_response, create_error_response,
    validate_mcp_protocol_version, JsonRpcError
)

# Import concurrency control from main server
from server import READ_TOOLS, TOOL_TABLE_MAP


class ConcurrencyController:
    """
    Manages concurrent access to database resources with fine-grained locking.
    Queues requests instead of rejecting them.
    
    Strategy:
    - READ operations: Fully concurrent (no locking)
    - WRITE operations: Table-level locking (writes to different tables can run concurrently)
    - TRANSACTION operations: Global lock (to prevent deadlocks)
    """
    
    def __init__(self):
        # Table-level write locks (one lock per table)
        self._table_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Global transaction lock (for operations that need isolation)
        self._transaction_lock = asyncio.Lock()
        # Active read counter (for monitoring)
        self._active_reads = 0
        self._active_writes = 0
    
    def read_operation(self, operation_name: str):
        """Context manager for read operations (no locking)."""
        class ReadContext:
            def __init__(self, controller):
                self.controller = controller
            
            async def __aenter__(self):
                self.controller._active_reads += 1
                logger.debug(f"📖 Read operation started: {operation_name} (active reads: {self.controller._active_reads})")
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                self.controller._active_reads -= 1
                logger.debug(f"📖 Read operation finished: {operation_name} (active reads: {self.controller._active_reads})")
        
        return ReadContext(self)
    
    def write_operation(self, operation_name: str, tables: list[str]):
        """
        Context manager for write operations (table-level locking).
        Queues requests waiting for locks instead of rejecting.
        """
        class WriteContext:
            def __init__(self, controller, tables):
                self.controller = controller
                self.tables = sorted(tables)  # Sort to prevent deadlocks
                self.locks = []
            
            async def __aenter__(self):
                # Acquire locks in sorted order to prevent deadlocks
                # asyncio.Lock() automatically queues waiters
                for table in self.tables:
                    lock = self.controller._table_locks[table]
                    await lock.acquire()
                    self.locks.append(lock)
                
                self.controller._active_writes += 1
                logger.debug(f"✏️  Write operation started: {operation_name} on tables {self.tables} (active writes: {self.controller._active_writes})")
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                # Release locks in reverse order
                for lock in reversed(self.locks):
                    lock.release()
                
                self.controller._active_writes -= 1
                logger.debug(f"✏️  Write operation finished: {operation_name} (active writes: {self.controller._active_writes})")
        
        return WriteContext(self, tables)
    
    def transaction_operation(self, operation_name: str):
        """
        Context manager for transaction operations (global locking).
        Queues requests waiting for locks instead of rejecting.
        """
        class TransactionContext:
            def __init__(self, controller):
                self.controller = controller
            
            async def __aenter__(self):
                await self.controller._transaction_lock.acquire()
                logger.debug(f"🔒 Transaction operation started: {operation_name}")
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                self.controller._transaction_lock.release()
                logger.debug(f"🔓 Transaction operation finished: {operation_name}")
        
        return TransactionContext(self)


# HTTP transport has its own concurrency controller
concurrency = ConcurrencyController()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global state (initialized at startup)
db: Optional[DatabaseConnection] = None
repos: Optional[RepositoryContainer] = None
app = FastAPI(title="Journal MCP Server - Streamable HTTP")

# Add CORS middleware to handle OPTIONS preflight requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (adjust for production)
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["MCP-Protocol-Version"],
)


async def get_tools_list() -> list:
    """Get list of available MCP tools (cached)"""
    from tools import get_core_tool_catalog
    tools = get_core_tool_catalog()
    
    # Convert MCP Tool objects to dict for JSON serialization
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema
        }
        for tool in tools
    ]


async def call_tool_handler(name: str, arguments: dict[str, Any]) -> list:
    """
    Call tool handler with concurrency control.
    Reuses existing handler logic from server.py.
    
    Strategy:
    - READ operations: Fully concurrent (no locking)
    - WRITE operations: Table-level locking (queues if busy)
    - Unknown operations: Transaction lock for safety
    """
    from handlers import get_handler
    
    handler_info = get_handler(name)
    
    if not handler_info:
        raise ValueError(f"Unknown tool: {name}")
    
    handler, needs_db, needs_repos, needs_transactions = handler_info
    
    # Determine concurrency strategy
    is_read = name in READ_TOOLS
    is_write = name in TOOL_TABLE_MAP
    
    # Special handling for execute_sql_query - detect read vs write at runtime
    if name == 'execute_sql_query':
        query = arguments.get('query', '').strip().upper()
        is_read = query.startswith(('SELECT', 'WITH', 'EXPLAIN'))
        is_write = not is_read
    
    # Helper to execute the actual handler
    async def execute():
        if needs_db and needs_repos:
            return await handler(db, repos, arguments)
        elif needs_repos:
            return await handler(arguments, repos)
        elif needs_db:
            if name == "execute_sql_query":
                result, _ = await handler(db, {}, 0, arguments)
                return result
            else:
                return await handler(db, arguments)
        else:
            return await handler(arguments)
    
    # Execute with appropriate concurrency control
    if is_read:
        # READ operations: No locking, fully concurrent
        async with concurrency.read_operation(name):
            return await execute()
    
    elif is_write:
        # WRITE operations: Table-level locking (queues if busy)
        tables = TOOL_TABLE_MAP.get(name, [name])
        async with concurrency.write_operation(name, tables):
            return await execute()
    
    else:
        # Unknown operations: Use transaction lock for safety
        logger.warning(f"⚠️  Tool '{name}' not classified - using transaction lock for safety")
        async with concurrency.transaction_operation(name):
            return await execute()


async def handle_mcp_request(request_data: dict) -> dict:
    """
    Handle a single MCP JSON-RPC request.
    Routes to appropriate handler based on method.
    
    Returns JSON-RPC response dict.
    """
    method = request_data.get("method")
    params = request_data.get("params", {})
    request_id = request_data.get("id")
    
    try:
        # Route to appropriate handler
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "journal-mcp-server",
                    "version": "1.0.0"
                }
            }
            return create_success_response(request_id, result)
        
        elif method == "ping":
            # Ping notification - no response needed
            return None
        
        elif method == "tools/list":
            tools = await get_tools_list()
            return create_success_response(request_id, {"tools": tools})
        
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            # Log tool call for monitoring
            print(f"[TOOL_CALL] {tool_name}", flush=True)

            if not tool_name:
                return create_error_response(
                    request_id, JsonRpcError.INVALID_PARAMS, "Missing tool name"
                )
            
            # Call tool handler
            result = await call_tool_handler(tool_name, tool_args)
            
            # Convert TextContent objects to dict
            content_list = []
            for item in result:
                content_list.append({
                    "type": item.type,
                    "text": item.text
                })
            
            return create_success_response(request_id, {"content": content_list})
        
        elif method == "notifications/initialized":
            # Client notification that it's ready - no response needed
            return None
        
        else:
            return create_error_response(
                request_id, JsonRpcError.METHOD_NOT_FOUND, f"Unknown method: {method}"
            )
    
    except Exception as e:
        logger.error(f"Error handling method {method}: {e}", exc_info=True)
        return create_error_response(
            request_id, JsonRpcError.INTERNAL_ERROR, str(e)
        )


@app.post("/mcp")
async def mcp_post_endpoint(
    request: Request,
    mcp_protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version")
):
    """
    POST /mcp - Main MCP endpoint for JSON-RPC requests.
    
    Accepts:
    - Content-Type: application/json
    - MCP-Protocol-Version header (optional but recommended)
    
    Returns:
    - 202 Accepted (for notifications - no response body)
    - 200 OK with Content-Type: application/json (for non-streaming responses)
    - 200 OK with Content-Type: text/event-stream (for streaming responses - future)
    """
    
    # Validate protocol version if provided
    if mcp_protocol_version and not validate_mcp_protocol_version(mcp_protocol_version):
        return JSONResponse(
            status_code=HTTP_400_BAD_REQUEST,
            content=create_error_response(
                None, JsonRpcError.INVALID_REQUEST,
                f"Unsupported MCP protocol version: {mcp_protocol_version}"
            )
        )
    
    # Parse request body
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=HTTP_400_BAD_REQUEST,
            content=create_error_response(
                None, JsonRpcError.PARSE_ERROR, f"Invalid JSON: {str(e)}"
            )
        )
    
    # Validate JSON-RPC structure
    if not is_valid_jsonrpc(body):
        return JSONResponse(
            status_code=HTTP_400_BAD_REQUEST,
            content=create_error_response(
                body.get("id"), JsonRpcError.INVALID_REQUEST, "Invalid JSON-RPC request"
            )
        )
    
    # Check if notification (no response expected)
    if is_notification(body):
        # Handle notification asynchronously, return 202 immediately
        asyncio.create_task(handle_mcp_request(body))
        return Response(status_code=HTTP_202_ACCEPTED)
    
    # Handle request and return response
    response = await handle_mcp_request(body)
    
    if response is None:
        # Shouldn't happen for requests (only notifications), but handle gracefully
        return Response(status_code=HTTP_202_ACCEPTED)
    
    # For now, always return JSON (streaming SSE to be implemented later if needed)
    return JSONResponse(content=response)


@app.get("/mcp")
async def mcp_get_endpoint():
    """
    GET /mcp - Optional persistent SSE stream for server-initiated notifications.
    
    This is optional per MCP spec. Currently returns empty SSE stream.
    Can be extended later for server push notifications.
    """
    async def event_generator():
        # Keep connection alive with periodic comments
        while True:
            yield ": keepalive\n\n"
            await asyncio.sleep(30)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@app.get("/healthz")
async def health_check():
    """Health check endpoint (separate from /mcp per MCP guide)"""
    try:
        if db and db.pool:
            # Quick database connectivity check
            async with db.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            return JSONResponse(content={
                "status": "healthy",
                "database": "connected"
            })
        else:
            return JSONResponse(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                content={"status": "unhealthy", "error": "Database not initialized"}
            )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "unhealthy", "error": str(e)}
        )


async def initialize_server():
    """Initialize database and repositories"""
    global db, repos
    
    config = DatabaseConfig.from_environment()
    db = DatabaseConnection(config)
    await db.connect()
    repos = RepositoryContainer(db)
    
    logger.info(f"Connected to database: {config.database} at {config.host}")


async def shutdown_server():
    """Cleanup on shutdown"""
    global db
    if db:
        await db.disconnect()
        logger.info("Database connection closed")


def run_http_server(host: str = "127.0.0.1", port: int = 3333):
    """
    Run the MCP server with Streamable HTTP transport.

    Args:
        host: Host to bind to
        port: Port to listen on

    Note: In uvicorn 0.32+, lifespan startup events run BEFORE socket binding.
    The embedding model load has been moved to an async background task in
    MemoryService so startup completes in ~2s instead of ~30s, eliminating
    the race window where another process could steal the port.
    """

    @app.on_event("startup")
    async def startup_event():
        await initialize_server()
        logger.info(f"Journal MCP Server (HTTP) starting on http://{host}:{port}/mcp")

    @app.on_event("shutdown")
    async def shutdown_event():
        await shutdown_server()

    uvicorn.run(app, host=host, port=port, log_level="info")
