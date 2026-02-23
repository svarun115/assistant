"""
Google Workspace MCP Server — unified server for Calendar, Tasks, Gmail, Sheets.

Transport modes:
  stdio (default):  python src/server.py
  HTTP/SSE:         python src/server.py --http [--port 3000]
"""

import sys
import os
import asyncio
import logging
import tempfile

from mcp.server.fastmcp import FastMCP

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize logging to file (don't pollute stderr/stdout used by MCP stdio protocol)
log_file = os.path.join(tempfile.gettempdir(), 'google-workspace-mcp-server.log')
logging.basicConfig(
    level=logging.INFO,
    filename=log_file,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('google-workspace')

# Create the shared MCP server instance
mcp = FastMCP("google-workspace")

# Register tools from each service module
from src.services.calendar import register_tools as register_calendar
from src.services.tasks import register_tools as register_tasks
from src.services.gmail import register_tools as register_gmail
from src.services.sheets import register_tools as register_sheets

register_calendar(mcp)
register_tasks(mcp)
register_gmail(mcp)
register_sheets(mcp)

logger.info("Registered tools from: Calendar, Tasks, Gmail, Sheets")


def run_stdio():
    """Run in stdio mode (default — for Claude Code, agents, etc.)."""
    from src.auth import auth

    logger.info("Google Workspace MCP Server starting (stdio mode)...")

    # Validate token on startup
    try:
        auth.get_service('calendar', 'v3')
        logger.info("Token validated — auth is healthy")
    except RuntimeError as e:
        logger.warning("Startup token validation failed: %s", e)

    mcp.run(transport='stdio')


def run_http(port: int = 3000):
    """Run in HTTP/SSE mode (for server manager, legacy VSCode, etc.)."""
    import uvicorn
    from fastapi import FastAPI, Request as FastAPIRequest
    from fastapi.responses import JSONResponse
    from src.auth import auth

    app = FastAPI(title="Google Workspace MCP Server")
    reauth_in_progress = [False]

    async def _run_reauth():
        """Run the OAuth re-authentication flow in a background task."""
        from src.auth import authenticate
        print("[AUTH] Token invalid — launching re-authentication flow...", flush=True)
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, authenticate)
            auth._creds = None
            auth._services.clear()
            auth._healthy = True
            auth._error_msg = None
            auth.get_service('calendar', 'v3')
            logger.info("Re-authentication successful — auth is healthy")
            print("[AUTH] Re-authentication successful!", flush=True)
        except Exception as e:
            logger.error("Re-authentication failed: %s", e)
            print(f"[AUTH] Re-authentication failed: {e}", flush=True)
        finally:
            reauth_in_progress[0] = False

    @app.on_event("startup")
    async def startup_event():
        logger.info("Google Workspace MCP Server starting (HTTP mode, port %d)...", port)
        try:
            auth.get_service('calendar', 'v3')
            logger.info("Token validated — auth is healthy")
        except RuntimeError as e:
            logger.warning("Startup token validation failed: %s", e)
            reauth_in_progress[0] = True
            await _run_reauth()
        asyncio.create_task(auth.background_refresh_loop())
        logger.info("Background token refresh task started (every 45 min)")

    @app.get("/healthz")
    async def health():
        from src.cache import cache
        if not auth.healthy and not reauth_in_progress[0]:
            reauth_in_progress[0] = True
            asyncio.create_task(_run_reauth())
        return {
            "status": "ok" if auth.healthy else "degraded",
            "auth_healthy": auth.healthy,
            "auth_error": "Re-authentication in progress..." if reauth_in_progress[0] else auth.error_msg,
            "reauth_in_progress": reauth_in_progress[0],
            "cache_stats": cache.stats(),
            "services": ["calendar", "tasks", "gmail", "sheets"]
        }

    @app.post("/mcp")
    async def mcp_handler(request: FastAPIRequest):
        """Handle MCP JSON-RPC over HTTP."""
        try:
            body = await request.json()
            method = body.get("method")
            request_id = body.get("id")

            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "google-workspace", "version": "2.0.0"}
                    }
                }
            elif method == "tools/list":
                tools = []
                for tool in mcp._tool_manager.list_tools():
                    tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.parameters
                    })
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools}
                }
            elif method == "tools/call":
                params = body.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                print(f"[TOOL_CALL] {tool_name}", flush=True)
                try:
                    # call_tool returns (list[ContentBlock], dict) - we want the list
                    content_blocks, _ = await mcp.call_tool(tool_name, arguments)
                    # Convert ContentBlock objects to JSON format
                    content = []
                    for block in content_blocks:
                        if hasattr(block, 'text'):
                            content.append({"type": "text", "text": block.text})
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": content}
                    }
                except Exception as e:
                    return JSONResponse({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"}
                    })
            else:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"}
                })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id") if 'body' in dir() else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            })

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--http" in args:
        port = 3000
        if "--port" in args:
            idx = args.index("--port")
            if idx + 1 < len(args):
                port = int(args[idx + 1])
        # Also check PORT env var (for server manager)
        port = int(os.environ.get("PORT", port))
        run_http(port)
    else:
        run_stdio()
