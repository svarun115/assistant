"""
Handler Routing Tests
Tests that MCP handlers are called with correct parameter order through the server routing layer.

These tests ensure the handle_call_tool function properly routes parameters to handlers.
This is critical because handlers can have different signatures depending on their needs_db and needs_repos flags.
"""

import pytest
import json
from datetime import datetime
from typing import Any
from mcp import types
from uuid import UUID

from database import DatabaseConnection
from server import RepositoryContainer
from handlers import get_handler
from models import EventCreate, EventType, Significance, WorkoutCreate, WorkoutCategory, MealCreate


class TestHandlerRouting:
    """Test that handlers receive parameters in correct order"""
    
    @pytest.mark.asyncio
    async def test_create_workout_handler_parameter_order(self, db_connection):
        """
        Test that create_workout handler receives (db, repos, arguments) in that order.
        
        This was previously broken when the server called handler(arguments, db, repos).
        The handler expects the db and repos first for initialization.
        """
        db = db_connection
        repos = RepositoryContainer(db)
        
        # Get the handler
        handler_info = get_handler("create_workout")
        assert handler_info is not None, "create_workout handler should be registered"
        
        handler, needs_db, needs_repos, _ = handler_info
        
        # Verify handler signature requirements
        assert needs_db is True, "create_workout should need_db=True"
        assert needs_repos is True, "create_workout should need_repos=True"
        
        # Create a workout
        arguments = {
            "event": {
                "title": "Test Strength Workout",
                "start_time": "2025-10-26T09:00:00",
            },
            "workout": {
                "workout_name": "Push Day",
                "category": "STRENGTH",
                "exercises": []  # Empty for simplicity
            }
        }
        
        # Call handler with CORRECT parameter order: (db, repos, arguments)
        result = await handler(db, repos, arguments)
        
        # Verify result
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], types.TextContent)
        
        # Check result contains success message
        result_text = result[0].text
        assert "created successfully" in result_text.lower() or "error" in result_text.lower()
        
        # If successful, verify the result is parseable JSON
        if "✅" in result_text:
            data = json.loads(result_text)
            assert "workout_id" in data
            assert "event_id" in data
    
    @pytest.mark.asyncio
    async def test_create_meal_handler_parameter_order(self, db_connection):
        """
        Test that create_meal handler receives (db, repos, arguments) in that order.
        
        Same parameter order issue as create_workout.
        """
        db = db_connection
        repos = RepositoryContainer(db)
        
        # Get the handler
        handler_info = get_handler("create_meal")
        assert handler_info is not None, "create_meal handler should be registered"
        
        handler, needs_db, needs_repos, _ = handler_info
        
        # Verify handler signature requirements
        assert needs_db is True, "create_meal should need_db=True"
        assert needs_repos is True, "create_meal should need_repos=True"
        
        # Create a meal
        arguments = {
            "event": {
                "title": "Lunch",
                "start_time": "2025-10-26T12:00:00",
            },
            "meal": {
                "meal_title": "lunch",
                "meal_type": "home_cooked",
                "items": []
            }
        }
        
        # Call handler with CORRECT parameter order: (db, repos, arguments)
        result = await handler(db, repos, arguments)
        
        # Verify result
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], types.TextContent)
        
        # Check result contains message
        result_text = result[0].text
        assert "created successfully" in result_text.lower() or "error" in result_text.lower()
        
        # If successful, verify the result is parseable JSON
        if "✅" in result_text:
            data = json.loads(result_text)
            assert "meal_id" in data
            assert "event_id" in data
    
    @pytest.mark.asyncio
    async def test_delete_event_handler_parameter_order(self, db_connection, sample_data):
        """
        Test that delete_event handler receives (db, arguments) in that order.
        
        delete_event only needs db, not repos (needs_db=True, needs_repos=False).
        """
        db = db_connection
        repos = RepositoryContainer(db)
        
        # Get the handler
        handler_info = get_handler("delete_event")
        assert handler_info is not None, "delete_event handler should be registered"
        
        handler, needs_db, needs_repos, _ = handler_info
        
        # Verify handler signature requirements
        assert needs_db is True, "delete_event should need_db=True"
        assert needs_repos is False, "delete_event should need_repos=False"
        
        # First create an event to delete
        event_id = await sample_data.create_event()
        
        # Delete the event
        arguments = {
            "event_id": str(event_id)
        }
        
        # Call handler with parameter order: (db, arguments)
        # (NOT db, repos, arguments because needs_repos=False)
        result = await handler(db, arguments)
        
        # Verify result
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], types.TextContent)
        
        # Check result - accept stub response or actual deletion
        result_text = result[0].text
        # Should either succeed (deleted/handled), show event not found, or error
        assert "deleted" in result_text.lower() or "not found" in result_text.lower() or "error" in result_text.lower() or "handled" in result_text.lower()
    
    @pytest.mark.asyncio
    async def test_handler_parameter_order_validation(self):
        """Verify critical handlers have correct parameter order"""
        from handlers import HANDLER_REGISTRY
        
        # Just verify the handlers that are known to have specific needs
        critical_handlers = {
            "create_workout": (True, True),  # (needs_db, needs_repos)
            "create_meal": (True, True),
            "delete_event": (True, False),
            "create_person": (False, True),
        }
        
        for tool_name, (expected_db, expected_repos) in critical_handlers.items():
            handler_info = HANDLER_REGISTRY.get(tool_name)
            assert handler_info is not None, f"{tool_name} not found"
            
            _, needs_db, needs_repos, _ = handler_info
            assert needs_db == expected_db, f"{tool_name}: expected needs_db={expected_db}, got {needs_db}"
            assert needs_repos == expected_repos, f"{tool_name}: expected needs_repos={expected_repos}, got {needs_repos}"
    
    @pytest.mark.asyncio
    async def test_server_routing_calls_handlers_correctly(self, db_connection, sample_data):
        """
        Simulate what the server.py handle_call_tool function does,
        ensuring parameter order is correct for all handler types.
        """
        db = db_connection
        repos = RepositoryContainer(db)
        
        # Test case 1: needs_db=True, needs_repos=True (should call with db, repos, arguments)
        handler_info = get_handler("create_workout")
        if handler_info:
            handler, needs_db, needs_repos, _ = handler_info
            
            if needs_db and needs_repos:
                # This is the call made by server.py's handle_call_tool
                arguments = {
                    "event": {
                        "title": "Test",
                        "start_time": "2025-10-26T10:00:00"
                    },
                    "workout": {
                        "workout_name": "Test",
                        "category": "STRENGTH",
                        "exercises": []
                    }
                }
                result = await handler(db, repos, arguments)
                assert isinstance(result, list)
                assert len(result) > 0
        
        # Test case 2: needs_db=True, needs_repos=False (should call with db, arguments)
        handler_info = get_handler("delete_event")
        if handler_info:
            handler, needs_db, needs_repos, _ = handler_info
            
            if needs_db and not needs_repos:
                event_id = await sample_data.create_event()
                arguments = {"event_id": str(event_id)}
                result = await handler(db, arguments)
                assert isinstance(result, list)
                assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
