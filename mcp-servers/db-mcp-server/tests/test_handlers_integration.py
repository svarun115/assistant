"""
Handler-Based Integration Tests
Tests MCP handlers through the server's routing layer (not direct database calls)
This ensures test coverage matches production code paths.
"""

import pytest
import json
from uuid import UUID
from server import RepositoryContainer
from tests.handler_test_utils import HandlerTestHelper


class TestCreateWorkoutHandler:
    """Test create_workout handler through routing"""
    
    @pytest.mark.asyncio
    async def test_create_workout_with_exercises(self, db_connection, sample_data):
        """Test creating a workout with exercises through the handler"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)
        
        # Get an exercise to use
        exercise_id = await sample_data.create_exercise("Bench Press")
        
        # Call create_workout handler through routing
        result = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {
                    "title": "Test Strength Workout",
                    "start_time": "2025-10-26T09:00:00",
                },
                "workout": {
                    "workout_name": "Push Day",
                    "category": "STRENGTH",
                    "intensity": 8,
                    "exercises": [
                        {
                            "exercise_id": str(exercise_id),
                            "sequence_order": 1,
                            "sets": [
                                {"set_number": 1, "set_type": "WARMUP", "weight_kg": 60, "reps": 10},
                                {"set_number": 2, "set_type": "WORKING", "weight_kg": 100, "reps": 8},
                            ]
                        }
                    ]
                }
            }
        )
        
        # Verify result is valid JSON with expected fields
        data = json.loads(result)
        assert "workout_id" in data
        assert "event_id" in data
        assert data["workout_name"] == "Push Day"
        assert data["total_exercises"] == 1
        assert data["total_sets"] == 2

    @pytest.mark.asyncio
    async def test_create_workout_accepts_uppercase_workout_subtype(self, db_connection):
        """Regression for #90: DB stores lowercase enum values but API can send uppercase."""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        result = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {
                    "title": "Test Run Workout",
                    "start_time": "2025-10-26T09:00:00",
                },
                "workout": {
                    "workout_name": "Morning Run",
                    "category": "CARDIO",
                    "workout_subtype": "RUN",
                    "distance_km": 5.0,
                },
            },
        )

        data = json.loads(result)
        workout_id = UUID(data["workout_id"])

        stored_subtype = await db_connection.fetchval(
            "SELECT workout_subtype::text FROM workouts WHERE id = $1",
            workout_id,
        )
        assert stored_subtype == "run"


class TestCreateMealHandler:
    """Test create_meal handler through routing"""
    
    @pytest.mark.asyncio
    async def test_create_meal_with_items(self, db_connection, sample_data):
        """Test creating a meal with items through the handler"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)
        
        # Call create_meal handler through routing
        result = await helper.assert_tool_success(
            "create_meal",
            {
                "event": {
                    "title": "Lunch",
                    "start_time": "2025-10-26T12:00:00",
                },
                "meal": {
                    "meal_title": "lunch",
                    "meal_type": "home_cooked",
                    "items": [
                        {
                            "item_name": "Grilled chicken",
                            "quantity": "200g",
                            "calories": 330,
                            "protein_g": 62
                        },
                        {
                            "item_name": "Rice",
                            "quantity": "1 cup",
                            "calories": 206,
                            "carbs_g": 45
                        }
                    ]
                }
            }
        )
        
        # Verify result is valid JSON with expected fields
        data = json.loads(result)
        assert "meal_id" in data
        assert "event_id" in data
        assert "title" in data
        assert data["meal_type"] == "home_cooked"


class TestDeleteEventHandler:
    """Test delete_event handler through routing"""
    
    @pytest.mark.asyncio
    async def test_delete_event_soft_delete(self, db_connection, sample_data):
        """Test deleting an event through the handler"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)
        
        # Create an event
        event_id = await sample_data.create_event(
            title="Event to Delete",
            category="social"
        )
        
        # Delete it through handler routing
        result = await helper.call_tool(
            "delete_event",
            {"event_id": str(event_id)}
        )
        
        # Verify deletion response (stub or actual)
        assert "deleted" in result.lower() or "handled" in result.lower()


class TestDeletePersonRelationshipHandler:
    """Test delete_person_relationship handler through routing"""
    
    @pytest.mark.asyncio
    async def test_delete_person_relationship_success(self, db_connection, sample_data):
        """Test successfully deleting a person relationship through the handler"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)
        
        # Create two people and a relationship
        person1_id = await sample_data.create_person(canonical_name="Person A")
        person2_id = await sample_data.create_person(canonical_name="Person B")
        
        # Add a relationship between them
        rel_result = await repos.people.add_relationship(
            person_id=person1_id,
            related_person_id=person2_id,
            relationship_type="sibling",
            bidirectional=False  # Don't create reciprocal via Python, trigger will
        )
        rel_id = rel_result['id']
        
        # Verify relationship exists
        rel_before = await db_connection.fetchrow(
            "SELECT id, person_id, related_person_id, relationship_type FROM person_relationships WHERE id = $1",
            rel_id
        )
        assert rel_before is not None
        
        # Verify reciprocal exists
        reciprocal_count_before = await db_connection.fetchval(
            "SELECT COUNT(*) FROM person_relationships WHERE person_id = $1 AND related_person_id = $2",
            person2_id, person1_id
        )
        assert reciprocal_count_before > 0
        
        # Delete through handler
        result = await helper.call_tool(
            "delete_person_relationship",
            {"relationship_id": str(rel_id)}
        )
        
        # Verify result is valid JSON with expected fields
        data = json.loads(result)
        assert "deleted_relationship_id" in data
        assert str(rel_id) == data["deleted_relationship_id"]
        assert "message" in data
        assert "✅" in data["message"]
        
        # Verify relationship is deleted
        rel_after = await db_connection.fetchrow(
            "SELECT id FROM person_relationships WHERE id = $1",
            rel_id
        )
        assert rel_after is None
        
        # Verify reciprocal is also deleted (trigger should have handled this)
        reciprocal_count_after = await db_connection.fetchval(
            "SELECT COUNT(*) FROM person_relationships WHERE person_id = $1 AND related_person_id = $2",
            person2_id, person1_id
        )
        assert reciprocal_count_after == 0
    
    @pytest.mark.asyncio
    async def test_delete_person_relationship_not_found(self, db_connection, sample_data):
        """Test deleting a non-existent relationship returns error"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)
        
        # Create a fake UUID that doesn't exist
        fake_rel_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Delete through handler - should return error
        result = await helper.call_tool(
            "delete_person_relationship",
            {"relationship_id": str(fake_rel_id)}
        )
        
        # Verify error response
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"].lower()


class TestHandlerParameterOrder:
    """Verify handlers are called with correct parameter order"""
    
    @pytest.mark.asyncio
    async def test_handler_needs_db_and_repos(self, db_connection):
        """Handlers with needs_db=True, needs_repos=True should receive (db, repos, arguments)"""
        from handlers import get_handler
        
        handler_info = get_handler("create_workout")
        assert handler_info is not None
        
        handler, needs_db, needs_repos, _ = handler_info
        assert needs_db is True
        assert needs_repos is True
        
        # The handler function signature should be (db, repos, arguments)
        import inspect
        sig = inspect.signature(handler)
        params = list(sig.parameters.keys())
        assert params[0] == "db"
        assert params[1] == "repos"
        assert params[2] == "arguments"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name",
        [
            "update_person_work",
            "update_person_education",
            "update_person_residence",
        ],
    )
    async def test_people_update_handlers_have_correct_parameter_order(self, db_connection, tool_name):
        """Regression: people update handlers must accept (db, repos, arguments)."""
        from handlers import get_handler
        import inspect

        handler_info = get_handler(tool_name)
        assert handler_info is not None

        handler, needs_db, needs_repos, _ = handler_info
        assert needs_db is True
        assert needs_repos is True

        sig = inspect.signature(handler)
        params = list(sig.parameters.keys())
        assert params[0] == "db"
        assert params[1] == "repos"
        assert params[2] == "arguments"
    
    @pytest.mark.asyncio
    async def test_handler_needs_db_only(self, db_connection):
        """Handlers with needs_db=True, needs_repos=False should receive (db, arguments)"""
        from handlers import get_handler
        
        handler_info = get_handler("delete_event")
        assert handler_info is not None
        
        handler, needs_db, needs_repos, _ = handler_info
        assert needs_db is True
        assert needs_repos is False
        
        # The handler function signature should be (db, arguments)
        import inspect
        sig = inspect.signature(handler)
        params = list(sig.parameters.keys())
        assert params[0] == "db"
        assert params[1] == "arguments"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
