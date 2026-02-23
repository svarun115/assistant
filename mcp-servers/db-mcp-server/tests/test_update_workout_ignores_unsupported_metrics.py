import json

import pytest
from server import RepositoryContainer
from tests.handler_test_utils import HandlerTestHelper


class TestUpdateWorkoutValidParams:
    """
    Test that update_workout properly updates valid fields.
    
    Note: Phantom params (intensity, pace, avg_heart_rate, max_heart_rate, distance_km)
    were removed from the tool schema in Issue #104. The tool now only accepts
    params that map to actual DB columns.
    """
    
    @pytest.mark.asyncio
    async def test_update_workout_valid_fields(self, db_connection, sample_data):
        """Test updating valid workout fields like category and workout_subtype"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create a workout (needs at least one valid exercise)
        exercise_id = await sample_data.create_exercise("Bench Press")
        create_result = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {"title": "Test Workout", "start_time": "2025-12-20T09:00:00"},
                "workout": {
                    "workout_name": "Push Day",
                    "category": "STRENGTH",
                    "exercises": [
                        {
                            "exercise_id": str(exercise_id),
                            "sequence_order": 1,
                            "sets": [{"set_number": 1, "set_type": "WORKING", "weight_kg": 100, "reps": 5}],
                        }
                    ],
                },
            },
        )
        workout_id = json.loads(create_result)["workout_id"]
        event_id = json.loads(create_result)["event_id"]

        # Update valid fields
        update_result = await helper.assert_tool_success(
            "update_workout",
            {
                "workout_id": workout_id,
                "category": "MIXED",
                "workout_subtype": "GYM_STRENGTH",
            },
        )

        update_data = json.loads(update_result)
        assert update_data["workout_id"] == workout_id
        assert update_data["event_id"] == event_id
        assert "successfully" in update_data["message"].lower()
        # Should NOT have ignored_fields since we removed that behavior
        assert "ignored_fields" not in update_data

    @pytest.mark.asyncio
    async def test_update_workout_external_linking(self, db_connection, sample_data):
        """Test linking workout to external system like Garmin"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create a workout
        exercise_id = await sample_data.create_exercise("Running")
        create_result = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {"title": "Morning Run", "start_time": "2025-12-20T07:00:00"},
                "workout": {
                    "workout_name": "5K Run",
                    "category": "CARDIO",
                    "workout_subtype": "RUN",
                    "exercises": [
                        {
                            "exercise_id": str(exercise_id),
                            "sequence_order": 1,
                            "sets": [{"set_number": 1, "duration_s": 1800, "reps": 1}],
                        }
                    ],
                },
            },
        )
        workout_id = json.loads(create_result)["workout_id"]

        # Link to Garmin
        update_result = await helper.assert_tool_success(
            "update_workout",
            {
                "workout_id": workout_id,
                "external_event_id": "20007876401",
                "external_event_source": "garmin",
            },
        )

        update_data = json.loads(update_result)
        assert update_data["external_event_id"] == "20007876401"
        assert update_data["external_event_source"] == "garmin"

    @pytest.mark.asyncio
    async def test_update_workout_no_fields_warning(self, db_connection, sample_data):
        """Test that updating with no valid fields returns appropriate warning"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create a workout
        exercise_id = await sample_data.create_exercise("Squat")
        create_result = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {"title": "Leg Day", "start_time": "2025-12-20T10:00:00"},
                "workout": {
                    "workout_name": "Leg Day",
                    "category": "STRENGTH",
                    "exercises": [
                        {
                            "exercise_id": str(exercise_id),
                            "sequence_order": 1,
                            "sets": [{"set_number": 1, "set_type": "WORKING", "weight_kg": 100, "reps": 5}],
                        }
                    ],
                },
            },
        )
        workout_id = json.loads(create_result)["workout_id"]

        # Try to update with only workout_id (no actual changes)
        result = await helper.call_tool(
            "update_workout",
            {
                "workout_id": workout_id,
            },
        )

        # Should get a warning about no fields to update
        assert "no fields to update" in result.lower()
