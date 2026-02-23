import json
from uuid import UUID

import pytest

from server import RepositoryContainer
from tests.handler_test_utils import HandlerTestHelper


class TestUpdateEventWorkoutNotes:
    @pytest.mark.asyncio
    async def test_update_event_updates_notes_for_workout_event(self, db_connection):
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        created_json = await helper.assert_tool_success(
            "create_workout",
            {
                "event": {
                    "title": "Workout With Notes",
                    "start_time": "2025-10-26T09:00:00",
                    "notes": "original notes",
                },
                "workout": {
                    "workout_name": "Notes Session",
                    "category": "STRENGTH",
                },
            },
        )

        created = json.loads(created_json)
        event_id = UUID(created["event_id"])

        await helper.assert_tool_success(
            "update_event",
            {
                "event_id": str(event_id),
                "notes": "updated notes",
            },
        )

        stored_notes = await db_connection.fetchval(
            "SELECT notes FROM events WHERE id = $1",
            event_id,
        )
        assert stored_notes == "updated notes"
