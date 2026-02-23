"""
Handler Testing Utilities

This module provides utilities for testing MCP handlers through the server's
routing layer (like production code does), not via direct repository calls.

This ensures tests match real-world usage patterns and catch parameter order
and routing bugs.
"""

from typing import Any, Dict, Optional
import logging
from mcp import types

from database import DatabaseConnection
from server import RepositoryContainer
from handlers import get_handler

logger = logging.getLogger(__name__)


class HandlerTestHelper:
    """Helper for calling handlers through the routing layer like the real server does"""
    
    def __init__(self, db: DatabaseConnection, repos: Optional[RepositoryContainer] = None):
        self.db = db
        self.repos = repos or RepositoryContainer(db)
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Call a handler through the routing layer.
        
        This simulates what server.py's handle_call_tool() does:
        1. Look up handler from registry
        2. Check needs_db and needs_repos flags
        3. Call handler with correct parameter order
        4. Return result as text
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments dict to pass to handler
        
        Returns:
            Result text from the handler
        
        Raises:
            ValueError: If handler not found or execution fails
        """
        try:
            # Look up handler
            handler_info = get_handler(tool_name)
            
            if not handler_info:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            handler, needs_db, needs_repos, needs_transactions = handler_info
            
            # Call handler with correct parameter order based on flags
            # IMPORTANT: Must match server.py's handle_call_tool() routing logic exactly
            if needs_db and needs_repos:
                # Handlers that need BOTH database and repository instances
                # (e.g., create_event, create_meal)
                result = await handler(self.db, self.repos, arguments)
            
            elif needs_repos:
                # Handlers that need repository instances but not database
                # (e.g., create_person, add_person_note, update_person)
                # NOTE: arguments comes FIRST, then repos!
                result = await handler(arguments, self.repos)
            
            elif needs_db:
                # Handlers that need database connection only
                # Special case: execute_sql_query has different signature
                if tool_name == "execute_sql_query":
                    result, _ = await handler(self.db, {}, 0, arguments)
                else:
                    result = await handler(self.db, arguments)
            
            else:
                # Discovery tools - no database required
                result = await handler(arguments)
            
            # Extract text from result
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], types.TextContent):
                    return result[0].text
            
            return str(result)
        
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            raise
    
    async def assert_tool_success(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        should_contain: Optional[str] = None
    ) -> str:
        """
        Call a handler and assert it succeeds.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass
            should_contain: Optional string that result must contain
        
        Returns:
            Result text
        
        Raises:
            AssertionError if tool fails or result doesn't contain expected string
        """
        result = await self.call_tool(tool_name, arguments)
        
        # Check for errors
        assert "error" not in result.lower(), f"Tool {tool_name} returned error: {result}"
        
        if should_contain:
            assert should_contain.lower() in result.lower(), \
                f"Expected '{should_contain}' in result, got: {result}"
        
        return result
    
    async def assert_tool_error(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        should_contain: Optional[str] = None
    ) -> str:
        """
        Call a handler and assert it fails.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass
            should_contain: Optional string that error must contain
        
        Returns:
            Error result text
        
        Raises:
            AssertionError if tool succeeds when it should fail
        """
        result = await self.call_tool(tool_name, arguments)
        
        # Check for errors
        assert "error" in result.lower(), \
            f"Tool {tool_name} should have failed but succeeded: {result}"
        
        if should_contain:
            assert should_contain.lower() in result.lower(), \
                f"Expected error to contain '{should_contain}', got: {result}"
        
        return result


async def call_handler(
    handler_name: str,
    arguments: Dict[str, Any],
    db: DatabaseConnection,
    repos: Optional[RepositoryContainer] = None
) -> str:
    """
    Convenience function to call a handler through routing.
    
    This is shorthand for HandlerTestHelper(db, repos).call_tool(handler_name, arguments)
    """
    helper = HandlerTestHelper(db, repos)
    return await helper.call_tool(handler_name, arguments)
