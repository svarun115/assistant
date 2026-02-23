"""
MCP Server Entry Point for Personal Journal Database
Run with: python server.py
"""

import asyncio
import logging
import json
import os
import sys
from pathlib import Path
from typing import Any, Set
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp import types

from database import DatabaseConnection
from config import DatabaseConfig
from container import RepositoryContainer

__version__ = "1.0.1"

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize server
app = Server("journal-mcp-server")
db: DatabaseConnection = None
repos = None

# Query logging for identifying missing tool coverage
query_log_path = Path(__file__).parent / "query_logs"
query_log_path.mkdir(exist_ok=True)

# ============================================================================
# CONCURRENCY CONTROL
# ============================================================================

class ConcurrencyController:
    """
    Manages concurrent access to database resources with fine-grained locking.
    
    Strategy:
    - READ operations: Fully concurrent (no locking)
    - WRITE operations: Table-level locking (writes to different tables can run concurrently)
    - TRANSACTION operations: Global lock (to prevent deadlocks)
    
    This allows maximum concurrency while preventing connection pool corruption.
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
        
        Args:
            operation_name: Name of the operation for logging
            tables: List of table names being modified (for lock acquisition)
        """
        class WriteContext:
            def __init__(self, controller, tables):
                self.controller = controller
                self.tables = sorted(tables)  # Sort to prevent deadlocks
                self.locks = []
            
            async def __aenter__(self):
                # Acquire locks in sorted order to prevent deadlocks
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
        Use for operations that need full isolation or involve multiple tables.
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

# Global concurrency controller
concurrency = ConcurrencyController()

# Tool operation classification
READ_TOOLS = {
    'execute_sql_query',  # Reads (SELECT queries detected at runtime)
    'get_database_schema',
    'query',              # Structured query tool (QUERY_MODE=structured)
    'aggregate',          # Structured aggregate tool (QUERY_MODE=structured)
    'search_exercises',
    'search_people',
    'search_locations',
    'get_recent_workouts',
    'get_recent_meals',
    'get_recent_events',
    'search_journal_history',
    'semantic_search',        # Renamed alias in structured mode
    'get_journal_by_date',
    'get_plan_vs_actual',
    'get_planning_insights',
}


# List of all tables for global operations (like restore)
ALL_TABLES = [
    'events', 'event_participants', 
    'workouts', 'workout_exercises', 'exercise_sets', 
    'meals', 'meal_items', 
    'commutes', 
    'entertainment', 
    'people', 'person_relationships', 'person_notes', 'work_history', 'education_history', 
    'locations', 
    'health_conditions', 'health_condition_logs', 'health_medicines', 'health_supplements',
    'exercises',
    'journal_entries',
    'daily_plans', 'planned_items'
]


# Map tools to their affected tables for write locking
TOOL_TABLE_MAP = {
    # Event operations
    'create_event': ['events', 'event_participants'],
    'update_event': ['events', 'event_participants'],

    # Workout operations
    'create_workout': ['events', 'event_participants', 'workouts', 'workout_exercises', 'exercise_sets'],
    'update_workout': ['workouts', 'workout_exercises', 'exercise_sets'],
    'reassign_exercise_in_workouts': ['workouts', 'workout_exercises'],

    # Meal operations
    'create_meal': ['events', 'event_participants', 'meals', 'meal_items'],
    'update_meal': ['meals', 'meal_items'],

    # Commute operations
    'create_commute': ['events', 'event_participants', 'commutes'],
    'update_commute': ['commutes'],

    # Entertainment operations
    'create_entertainment': ['events', 'event_participants', 'entertainment'],

    # People operations
    'create_person': ['people'],
    'update_person': ['people'],
    'merge_duplicate_people': ['people', 'event_participants', 'person_relationships'],
    'add_person_relationship': ['person_relationships'],
    'update_person_relationship': ['person_relationships'],
    'add_person_note': ['person_notes'],
    'update_person_note': ['person_notes'],
    'add_person_work': ['work_history'],
    'update_person_work': ['work_history'],
    'add_person_education': ['education_history'],
    'update_person_education': ['education_history'],
    'add_person_residence': ['person_residences', 'temporal_locations'],
    'update_person_residence': ['person_residences'],

    # Location operations
    'create_location': ['locations'],
    'update_location': ['locations'],

    # Health operations
    'log_health_condition': ['health_conditions'],
    'update_health_condition': ['health_conditions'],
    'log_medicine': ['health_medicines'],
    'update_medicine': ['health_medicines'],
    'log_supplement': ['health_supplements'],
    'update_supplement': ['health_supplements'],
    'log_health_condition_update': ['health_condition_logs'],
    'update_health_condition_log': ['health_condition_logs'],

    # Exercise operations
    'create_exercise': ['exercises'],
    'update_exercise': ['exercises'],

    # Unified entity delete/restore (replaces 23 individual delete/undelete tools)
    'delete_entity': [
        'events', 'workouts', 'meals', 'commutes', 'people', 'person_relationships',
        'person_residences', 'exercises', 'locations', 'journal_entries',
        'health_conditions', 'health_medicines', 'health_supplements', 'health_condition_logs'
    ],
    'restore_entity': [
        'events', 'workouts', 'meals', 'commutes', 'people', 'person_residences',
        'exercises', 'locations', 'journal_entries'
    ],

    # Journal operations
    'log_journal_entry': ['journal_entries'],

    # Planning operations
    'create_daily_plan': ['daily_plans', 'planned_items'],
    'update_plan_item': ['planned_items'],

}



def log_raw_query(query: str, params: list = None, query_type: str = "SELECT"):
    """
    Log raw SQL queries to identify patterns and missing tool coverage.
    Logs are written to query_logs/ directory with daily rotation.
    """
    try:
        log_file = query_log_path / f"queries_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query_type": query_type,
            "query": query.strip(),
            "params": params or [],
            "query_hash": hash(query.strip())  # For deduplication analysis
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    except Exception as e:
        logger.warning(f"Failed to log query: {e}")


def serialize_result(obj):
    """Helper to serialize datetime and other non-JSON types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available MCP tools using lazy discovery pattern.
    
    Returns core tools including:
    - Core database operations (execute_sql_query READ-ONLY, get_database_schema)
    - Entity resolution (search_exercises, search_people, search_locations)
    - Entity creation (create_event, create_workout, create_meal)
    - Discovery tools (discover_workout_tools, discover_meal_tools, etc.)
    - People management (create_person, add_person_note, etc.)
    
    REMOVED: propose_write_query, confirm_write_query, list_pending_writes, cancel_write_query
    Reason: All data writes now go through specialized creation tools for safety.
    
    Specialized tools (workouts, meals, events, travel, entertainment) are
    discovered on-demand via discovery tools to reduce token usage and
    improve LLM performance.
    """
    from tools import get_core_tool_catalog
    return get_core_tool_catalog()


@app.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """List available prompts - system instructions for the LLM"""
    return [
        types.Prompt(
            name="journal_system_instructions",
            description="Complete system instructions for using the Personal Journal Database. Includes event-centric architecture, database schema, extraction examples, query patterns, and best practices. Read this first to understand how to work with the database.",
            arguments=[]
        )
    ]


@app.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, Any] | None
) -> types.GetPromptResult:
    """Get prompt content - returns the combined system instructions"""
    
    if name == "journal_system_instructions":
        try:
            prompts_dir = Path(__file__).parent / "mcp" / "prompts"
            files_to_load = ["CAPABILITIES.md", "WORKFLOW.md", "EXAMPLES.md"]
            content_parts = []

            for filename in files_to_load:
                file_path = prompts_dir / filename
                if file_path.exists():
                    with open(file_path, "r", encoding="utf-8") as f:
                        content_parts.append(f.read())
                else:
                    logger.warning(f"Instruction file not found: {filename}")

            if not content_parts:
                # Fallback if no files found (or maybe INSTRUCTIONS.md still exists in some envs)
                fallback_path = prompts_dir / "INSTRUCTIONS.md"
                if fallback_path.exists():
                     with open(fallback_path, "r", encoding="utf-8") as f:
                        content_parts.append(f.read())
                else:
                    return types.GetPromptResult(
                        description="Instructions files not found",
                        messages=[
                            types.PromptMessage(
                                role="user",
                                content=types.TextContent(
                                    type="text",
                                    text="ERROR: Instruction files (CAPABILITIES.md, WORKFLOW.md, EXAMPLES.md) not found in mcp/prompts/."
                                )
                            )
                        ]
                    )
            
            full_content = "\n\n---\n\n".join(content_parts)
            
            return types.GetPromptResult(
                description="Personal Journal Database - Complete System Instructions",
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=full_content
                        )
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Error reading instructions: {e}")
            return types.GetPromptResult(
                description="Error reading instructions",
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=f"ERROR: Could not read instructions: {str(e)}"
                        )
                    )
                ]
            )
    else:
        raise ValueError(f"Unknown prompt: {name}")


@app.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    """
    Handle tool execution with intelligent concurrency control.
    
    Strategy:
    - READ operations: Fully concurrent
    - WRITE operations: Table-level locking (concurrent if different tables)
    - Unknown/complex operations: Global transaction lock
    
    All tool handlers are organized in the handlers/ directory by category.
    """
    
    try:
        # Import handler registry
        from handlers import get_handler
        
        # Look up handler
        handler_info = get_handler(name)
        
        if not handler_info:
            return [types.TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]
        
        handler, needs_db, needs_repos, needs_transactions = handler_info
        
        # Determine concurrency strategy based on tool type
        is_read = name in READ_TOOLS
        is_write = name in TOOL_TABLE_MAP
        
        # Special handling for execute_sql_query - detect read vs write at runtime
        if name == 'execute_sql_query':
            query = arguments.get('query', '').strip().upper()
            is_read = query.startswith(('SELECT', 'WITH', 'EXPLAIN'))
            is_write = not is_read
        
        # Execute with appropriate concurrency control
        if is_read:
            # READ operations: No locking, fully concurrent
            async with concurrency.read_operation(name):
                result = await _execute_handler(name, handler, needs_db, needs_repos, arguments)
                return result
        
        elif is_write:
            # WRITE operations: Table-level locking
            tables = TOOL_TABLE_MAP.get(name, [name])  # Fallback to tool name if not mapped
            async with concurrency.write_operation(name, tables):
                result = await _execute_handler(name, handler, needs_db, needs_repos, arguments)
                return result
        
        else:
            # Unknown operations: Use transaction lock for safety
            logger.warning(f"⚠️  Tool '{name}' not classified - using transaction lock for safety")
            async with concurrency.transaction_operation(name):
                result = await _execute_handler(name, handler, needs_db, needs_repos, arguments)
                return result
            
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        # Enhance error message for better user experience (Issues #101, #102)
        from utils.error_messages import enhance_error_message
        enhanced_msg = enhance_error_message(e)
        return [types.TextContent(
            type="text",
            text=f"Error executing {name}: {enhanced_msg}"
        )]


async def _execute_handler(
    name: str,
    handler,
    needs_db: bool,
    needs_repos: bool,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Execute the actual handler with proper argument passing."""
    
    # Build handler arguments based on requirements
    if needs_db and needs_repos:
        # Handlers that need BOTH database and repository instances
        return await handler(db, repos, arguments)
    
    elif needs_repos:
        # Handlers that need repository instances but not database
        return await handler(arguments, repos)
    
    elif needs_db:
        # Standard handlers that need database connection
        if name == "execute_sql_query":
            result, _ = await handler(db, {}, 0, arguments)
            return result
        else:
            return await handler(db, arguments)
    
    else:
        # Discovery tools - no database required
        return await handler(arguments)


# ============================================================================
# DEPRECATED - Old monolithic handler code removed
# All handlers now in handlers/ directory for better maintainability
# ============================================================================
# ============================================================================
# MCP RESOURCES - Detailed LLM Instructions
# ============================================================================

@app.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available instruction/documentation resources"""
    resources_dir = Path(__file__).parent / "mcp" / "resources"
    
    resources = []
    
    # Add all markdown files from mcp/resources/
    if resources_dir.exists():
        for md_file in resources_dir.glob("*.md"):
            resources.append(
                types.Resource(
                    uri=f"instruction://{md_file.stem}",
                    name=md_file.stem.replace("_", " ").title(),
                    description=f"Detailed instructions for {md_file.stem.replace('_', ' ').lower()}",
                    mimeType="text/markdown"
                )
            )
    
    return resources


@app.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read instruction/documentation resource content"""
    if not uri.startswith("instruction://"):
        raise ValueError(f"Unknown resource URI: {uri}")
    
    # Extract filename from URI
    resource_name = uri.replace("instruction://", "")
    resources_dir = Path(__file__).parent / "mcp" / "resources"
    file_path = resources_dir / f"{resource_name}.md"
    
    if not file_path.exists():
        raise FileNotFoundError(f"Resource not found: {resource_name}")
    
    # Read and return the markdown content
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return content


async def main():
    """Main entry point for MCP server"""
    global db, repos
    
    try:
        # Load database configuration (environment-aware)
        # Note: config.py handles loading .env.{mode} based on APP_ENV
        config = DatabaseConfig.from_environment()
        env_mode = os.getenv('APP_ENV', 'development')
        
        # Initialize database connection
        db = DatabaseConnection(config)
        await db.connect()
        
        # Initialize repository container
        repos = RepositoryContainer(db)
        
        logger.info("Journal MCP Server starting...")
        logger.info(f"Environment: {env_mode}")
        logger.info(f"Connected to database: {config.database} at {config.host}")
        
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="journal-mcp-server",
                    server_version="1.0.0",
                    capabilities=app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}", exc_info=True)
        raise
    finally:
        if db:
            await db.disconnect()
            logger.info("Database connection closed")


def cli_entry():
    """Entry point for console script - wraps async main()"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Journal MCP Server")
    parser.add_argument('--version', '-v', action='store_true', help='Show version')
    parser.add_argument('--http', action='store_true', help='Run in HTTP mode (Streamable HTTP transport)')
    parser.add_argument('--port', type=int, default=3333, help='Port for HTTP mode (default: 3333)')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Host for HTTP mode (default: 127.0.0.1)')
    
    args = parser.parse_args()
    
    # Handle --version flag
    if args.version:
        print(f"journal-mcp-server version {__version__}")
        sys.exit(0)
    
    # Handle --http flag for HTTP server mode (Streamable HTTP per MCP spec)
    if args.http:
        logger.info(f"Starting in HTTP mode (Streamable HTTP) on {args.host}:{args.port}/mcp")
        from transport.http import run_http_server
        run_http_server(host=args.host, port=args.port)
    else:
        # Default: stdio mode
        logger.info("Starting in stdio mode...")
        asyncio.run(main())


if __name__ == "__main__":
    cli_entry()
