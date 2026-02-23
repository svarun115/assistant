"""
Tests for reassign_exercise_in_workouts tool (Issue #105)

This tool allows reassigning exercise_id in workout_exercises table
for exercise deduplication/merging scenarios.
"""

import json
import pytest
from uuid import UUID

from server import RepositoryContainer
from tests.handler_test_utils import HandlerTestHelper


class TestReassignExerciseInWorkouts:
    """Tests for the reassign_exercise_in_workouts tool"""

    @pytest.mark.asyncio
    async def test_reassign_exercise_success(self, db_connection, sample_data):
        """Test successful reassignment of exercise_id in workout_exercises"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create two exercises (one duplicate, one canonical)
        duplicate_exercise_id = await sample_data.create_exercise("Pull Up")
        canonical_exercise_id = await sample_data.create_exercise("Pull-up")

        # Create a workout using the duplicate exercise
        create_result = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {"title": "Back Day", "start_time": "2025-12-20T09:00:00"},
                "workout": {
                    "workout_name": "Back Day",
                    "category": "STRENGTH",
                    "exercises": [
                        {
                            "exercise_id": str(duplicate_exercise_id),
                            "sequence_order": 1,
                            "sets": [
                                {"set_number": 1, "set_type": "WORKING", "reps": 10},
                                {"set_number": 2, "set_type": "WORKING", "reps": 8},
                            ],
                        }
                    ],
                },
            },
        )
        workout_id = json.loads(create_result)["workout_id"]

        # Reassign the exercise
        reassign_result = await helper.assert_tool_success(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": str(duplicate_exercise_id),
                "new_exercise_id": str(canonical_exercise_id),
            },
        )

        result_data = json.loads(reassign_result)
        assert result_data["old_exercise_id"] == str(duplicate_exercise_id)
        assert result_data["new_exercise_id"] == str(canonical_exercise_id)
        assert result_data["old_exercise_name"] == "Pull Up"
        assert result_data["new_exercise_name"] == "Pull-up"
        assert result_data["affected_workout_exercise_count"] == 1
        assert result_data["affected_workout_count"] == 1
        assert "reassigned" in result_data["message"].lower()

        # Verify in database that exercise_id was updated
        async with db_connection.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT exercise_id FROM workout_exercises 
                WHERE workout_id = (SELECT id FROM workouts WHERE id = $1)
                """,
                UUID(workout_id)
            )
            assert row["exercise_id"] == canonical_exercise_id

    @pytest.mark.asyncio
    async def test_reassign_exercise_multiple_workouts(self, db_connection, sample_data):
        """Test reassignment affects multiple workouts correctly"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create exercises
        duplicate_exercise_id = await sample_data.create_exercise("Kettlebell Row")
        canonical_exercise_id = await sample_data.create_exercise("Row")

        # Create multiple workouts using the duplicate exercise
        for i in range(3):
            await helper.assert_tool_success(
                "create_workout",
                {
                    "event": {"title": f"Workout {i+1}", "start_time": f"2025-12-{20+i}T09:00:00"},
                    "workout": {
                        "workout_name": f"Back Workout {i+1}",
                        "category": "STRENGTH",
                        "exercises": [
                            {
                                "exercise_id": str(duplicate_exercise_id),
                                "sequence_order": 1,
                                "sets": [{"set_number": 1, "set_type": "WORKING", "reps": 10}],
                            }
                        ],
                    },
                },
            )

        # Reassign the exercise
        reassign_result = await helper.assert_tool_success(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": str(duplicate_exercise_id),
                "new_exercise_id": str(canonical_exercise_id),
            },
        )

        result_data = json.loads(reassign_result)
        assert result_data["affected_workout_exercise_count"] == 3
        assert result_data["affected_workout_count"] == 3

    @pytest.mark.asyncio
    async def test_reassign_exercise_no_records(self, db_connection, sample_data):
        """Test reassignment when no workout_exercises reference the old exercise"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create two exercises but don't use either in any workout
        old_exercise_id = await sample_data.create_exercise("Unused Exercise 1")
        new_exercise_id = await sample_data.create_exercise("Unused Exercise 2")

        # Reassign - should succeed but affect 0 records
        reassign_result = await helper.assert_tool_success(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": str(old_exercise_id),
                "new_exercise_id": str(new_exercise_id),
            },
        )

        result_data = json.loads(reassign_result)
        assert result_data["affected_workout_exercise_count"] == 0
        assert result_data["affected_workout_count"] == 0
        assert "no workout_exercises" in result_data["message"].lower() or "0" in result_data["message"]

    @pytest.mark.asyncio
    async def test_reassign_exercise_old_not_found(self, db_connection, sample_data):
        """Test error when old_exercise_id doesn't exist"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create only the new exercise
        new_exercise_id = await sample_data.create_exercise("Valid Exercise")

        # Try to reassign from non-existent exercise
        result = await helper.assert_tool_error(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": "00000000-0000-0000-0000-000000000000",
                "new_exercise_id": str(new_exercise_id),
            },
            should_contain="not found"
        )

    @pytest.mark.asyncio
    async def test_reassign_exercise_new_not_found(self, db_connection, sample_data):
        """Test error when new_exercise_id doesn't exist"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # Create only the old exercise
        old_exercise_id = await sample_data.create_exercise("Old Exercise")

        # Try to reassign to non-existent exercise
        result = await helper.assert_tool_error(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": str(old_exercise_id),
                "new_exercise_id": "00000000-0000-0000-0000-000000000000",
            },
            should_contain="not found"
        )

    @pytest.mark.asyncio
    async def test_reassign_exercise_same_id_error(self, db_connection, sample_data):
        """Test error when old and new exercise IDs are the same"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        exercise_id = await sample_data.create_exercise("Some Exercise")

        # Try to reassign to itself
        result = await helper.assert_tool_error(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": str(exercise_id),
                "new_exercise_id": str(exercise_id),
            },
            should_contain="cannot be the same"
        )

    @pytest.mark.asyncio
    async def test_reassign_exercise_invalid_uuid(self, db_connection, sample_data):
        """Test error with invalid UUID format"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        new_exercise_id = await sample_data.create_exercise("Valid Exercise")

        # Try with invalid UUID
        result = await helper.assert_tool_error(
            "reassign_exercise_in_workouts",
            {
                "old_exercise_id": "not-a-valid-uuid",
                "new_exercise_id": str(new_exercise_id),
            },
            should_contain="invalid"
        )
