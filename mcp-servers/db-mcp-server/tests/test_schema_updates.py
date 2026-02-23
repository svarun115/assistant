
import pytest
import json
from uuid import UUID
from server import RepositoryContainer
from tests.handler_test_utils import HandlerTestHelper

class TestSchemaUpdates:
    """Test recent schema updates for kinship and interaction_mode"""

    @pytest.mark.asyncio
    async def test_person_kinship(self, db_connection):
        """Test creating and updating a person with kinship_to_owner"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # 1. Create person with kinship
        create_result = await helper.assert_tool_success(
            "create_person",
            {
                "canonical_name": "Jane Doe",
                "relationship": "family",
                "kinship_to_owner": "sister"
            }
        )
        create_data = json.loads(create_result)
        person_id = create_data["person_id"]

        # Verify in DB
        person = await repos.people.get_by_id(UUID(person_id))
        assert person.kinship_to_owner == "sister"

        # 2. Update person kinship
        update_result = await helper.assert_tool_success(
            "update_person",
            {
                "person_id": person_id,
                "kinship_to_owner": "mother"
            }
        )
        
        # Verify in DB
        person = await repos.people.get_by_id(UUID(person_id))
        assert person.kinship_to_owner == "mother"

    @pytest.mark.asyncio
    async def test_event_interaction_mode(self, db_connection):
        """Test creating and updating an event with interaction_mode"""
        repos = RepositoryContainer(db_connection)
        helper = HandlerTestHelper(db_connection, repos)

        # 1. Create a participant
        person_result = await helper.assert_tool_success(
            "create_person",
            {"canonical_name": "Meeting Participant"}
        )
        person_id = json.loads(person_result)["person_id"]

        # 2. Create event with interaction_mode
        create_result = await helper.assert_tool_success(
            "create_event",
            {
                "title": "Virtual Meeting",
                "start_time": "2025-12-01T10:00:00",
                "event_type": "work",
                "participant_ids": [person_id],
                "interaction_mode": "virtual_video"
            }
        )
        event_id = json.loads(create_result)["event_id"]

        # Verify in DB (need to query event_participants table directly or via repo if supported)
        # The repo.events.get_by_id returns an Event object which has a participants list
        event = await repos.events.get_by_id(UUID(event_id))
        assert len(event.participants) == 1
        assert event.participants[0].interaction_mode == "virtual_video"

        # 3. Update event interaction_mode
        update_result = await helper.assert_tool_success(
            "update_event",
            {
                "event_id": event_id,
                "participant_ids": [person_id],
                "interaction_mode": "in_person"
            }
        )

        # Verify in DB
        event = await repos.events.get_by_id(UUID(event_id))
        assert len(event.participants) == 1
        assert event.participants[0].interaction_mode == "in_person"
