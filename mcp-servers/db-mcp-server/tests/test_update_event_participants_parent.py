#!/usr/bin/env python3
"""
Test update_event tool with participant_ids and parent_event_id parameters.
Tests the fix for Issue #49.
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseConnection
from config import DatabaseConfig
from repositories import (
    PeopleRepository, LocationsRepository, EventsRepository
)
from models import EventCreate, EventType, Significance, EventParticipant
from handlers.event_handlers import handle_update_event
from datetime import datetime


class RepositoryContainer:
    def __init__(self, db):
        self.people = PeopleRepository(db)
        self.locations = LocationsRepository(db)
        self.events = EventsRepository(db)


async def run_test_logic(db):
    """Test updating event with participant_ids and parent_event_id"""
    
    repos = RepositoryContainer(db)
    
    try:
        print("Setting up test data...")
        print("=" * 80)
        
        # Create 3 people
        person1 = await repos.people.get_or_create("Alice")
        person2 = await repos.people.get_or_create("Bob")
        person3 = await repos.people.get_or_create("Charlie")
        
        print(f"✅ Created people: Alice ({person1.id}), Bob ({person2.id}), Charlie ({person3.id})")
        
        # Create a location
        location = await repos.locations.get_or_create("Test Restaurant")
        print(f"✅ Created location: Test Restaurant ({location.id})")
        
        # Create a parent event
        parent_event = EventCreate(
            event_type=EventType.GENERIC,
            title="Evening Social Event",
            start_time=datetime(2025, 6, 21, 18, 0),
            end_time=datetime(2025, 6, 21, 23, 0),
            location_id=location.id,
            significance=Significance.NOTABLE
        )
        created_parent = await repos.events.create(parent_event)
        print(f"✅ Created parent event: {created_parent.title} ({created_parent.id})")
        
        # Create a child event (initially without parent)
        child_event = EventCreate(
            event_type=EventType.GENERIC,
            title="Dinner",
            start_time=datetime(2025, 6, 21, 19, 0),
            end_time=datetime(2025, 6, 21, 21, 0),
            location_id=location.id,
            significance=Significance.ROUTINE,
            participants=[EventParticipant(person_id=person1.id, role="participant")]
        )
        created_child = await repos.events.create(child_event)
        print(f"✅ Created child event: {created_child.title} ({created_child.id})")
        print(f"   Initial participants: {[p.person_name for p in created_child.participants]}")
        
        print()
        print("TEST 1: Adding participants to event")
        print("-" * 80)
        
        # Test 1: Add participants
        result = await handle_update_event(
            db,
            repos,
            {
                "event_id": str(created_child.id),
                "participant_ids": [
                    str(person1.id),
                    str(person2.id),
                    str(person3.id)
                ]
            }
        )
        
        print(result[0].text)
        
        # Verify participants were added
        async with db.pool.acquire() as conn:
            participant_count = await conn.fetchval(
                "SELECT COUNT(*) FROM event_participants WHERE event_id = $1",
                created_child.id
            )
            assert participant_count == 3, f"Expected 3 participants, got {participant_count}"
        
        print("✅ TEST 1 PASSED: 3 participants added successfully")
        
        print()
        print("TEST 2: Setting parent_event_id for hierarchical relationship")
        print("-" * 80)
        
        # Test 2: Set parent event
        result = await handle_update_event(
            db,
            repos,
            {
                "event_id": str(created_child.id),
                "parent_event_id": str(created_parent.id)
            }
        )
        
        print(result[0].text)
        
        # Verify parent was set
        async with db.pool.acquire() as conn:
            parent_id = await conn.fetchval(
                "SELECT parent_event_id FROM events WHERE id = $1",
                created_child.id
            )
            assert parent_id == created_parent.id, f"Parent event ID mismatch"
        
        print("✅ TEST 2 PASSED: Parent event relationship established")
        
        print()
        print("TEST 3: Updating both participants and parent_event_id together")
        print("-" * 80)
        
        # Create another event
        another_event = EventCreate(
            event_type=EventType.GENERIC,
            title="Drinks",
            start_time=datetime(2025, 6, 21, 21, 30),
            end_time=datetime(2025, 6, 21, 22, 30),
            location_id=location.id,
            significance=Significance.ROUTINE
        )
        created_another = await repos.events.create(another_event)
        print(f"Created event: {created_another.title} ({created_another.id})")
        
        # Update both at once
        result = await handle_update_event(
            db,
            repos,
            {
                "event_id": str(created_another.id),
                "participant_ids": [str(person1.id), str(person2.id)],
                "parent_event_id": str(created_parent.id)
            }
        )
        
        print(result[0].text)
        
        # Verify both were updated
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT parent_event_id FROM events WHERE id = $1",
                created_another.id
            )
            participant_count = await conn.fetchval(
                "SELECT COUNT(*) FROM event_participants WHERE event_id = $1",
                created_another.id
            )
            assert row['parent_event_id'] == created_parent.id, "Parent not set"
            assert participant_count == 2, f"Expected 2 participants, got {participant_count}"
        
        print("✅ TEST 3 PASSED: Both fields updated successfully")
        
        print()
        print("=" * 80)
        print("✅ ALL TESTS PASSED!")
        print()
        print("Summary:")
        print(f"  - update_event now supports participant_ids parameter")
        print(f"  - update_event now supports parent_event_id parameter")
        print(f"  - Both can be updated independently or together")
        print(f"  - Issue #49 is resolved!")
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise


@pytest.mark.asyncio
async def test_update_event_with_new_parameters(db):
    await run_test_logic(db)


if __name__ == "__main__":
    async def main():
        config = DatabaseConfig.from_environment('test')
        db = DatabaseConnection(config)
        await db.connect()
        try:
            await run_test_logic(db)
        finally:
            await db.disconnect()
            
    asyncio.run(main())
