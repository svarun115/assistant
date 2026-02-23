#!/usr/bin/env python3
"""
Test create_event tool with parent_event_id parameter.
Tests the fix for Issue #63 - parent_event_id support in event creation and updates.
"""
import asyncio
import sys
import json
from pathlib import Path
from uuid import UUID
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseConnection
from config import DatabaseConfig
from repositories import (
    PeopleRepository, LocationsRepository, EventsRepository
)
from models import EventCreate, EventType, Significance
from handlers.event_handlers import handle_create_event, handle_update_event
from datetime import datetime


class RepositoryContainer:
    def __init__(self, db):
        self.people = PeopleRepository(db)
        self.locations = LocationsRepository(db)
        self.events = EventsRepository(db)


async def run_test_logic(db):
    """Test creating events with parent_event_id parameter"""
    
    repos = RepositoryContainer(db)
    
    try:
        print("=" * 80)
        print("TEST: create_event with parent_event_id support")
        print("=" * 80)
        print()
        
        # Create location
        location = await repos.locations.get_or_create("Hawaii")
        print(f"✅ Created location: Hawaii ({location.id})")
        
        # TEST 1: Create a parent event (trip)
        print()
        print("TEST 1: Create parent event (trip)")
        print("-" * 80)
        
        result = await handle_create_event(
            db,
            repos,
            {
                "event_type": "generic",
                "title": "Hawaii Trip",
                "start_time": "2025-06-06T00:00:00",
                "end_time": "2025-06-12T23:59:59",
                "category": "travel",
                "significance": "major_milestone",
                "location_id": str(location.id)
            }
        )
        
        response_text = result[0].text
        print(response_text)
        parent_event_data = json.loads(response_text)
        assert "event_id" in parent_event_data, "Parent event creation failed"
        parent_event_id = parent_event_data["event_id"]
        print(f"✅ TEST 1 PASSED: Parent event created: {parent_event_id}")
        
        # TEST 2: Create a child event with parent_event_id
        print()
        print("TEST 2: Create child event with parent_event_id")
        print("-" * 80)
        
        result = await handle_create_event(
            db,
            repos,
            {
                "event_type": "generic",
                "title": "Hiking on Kauai",
                "start_time": "2025-06-08T06:00:00",
                "end_time": "2025-06-08T17:00:00",
                "parent_event_id": parent_event_id,
                "category": "health",
                "significance": "notable",
                "location_id": str(location.id)
            }
        )
        
        response_text = result[0].text
        print(response_text)
        child_event_data = json.loads(response_text)
        assert "event_id" in child_event_data, "Child event creation failed"
        child_event_id = child_event_data["event_id"]
        print(f"✅ TEST 2 PASSED: Child event created: {child_event_id}")
        
        # Verify in database
        async with db.pool.acquire() as conn:
            child_row = await conn.fetchrow(
                "SELECT parent_event_id FROM events WHERE id = $1",
                UUID(child_event_id)
            )
            assert child_row is not None, "Child event not found"
            assert child_row['parent_event_id'] == UUID(parent_event_id), \
                f"Parent event ID mismatch: expected {parent_event_id}, got {child_row['parent_event_id']}"
        
        print(f"✅ Database verified: child event has parent_event_id = {parent_event_id}")
        
        # TEST 3: Update event to add parent_event_id
        print()
        print("TEST 3: Update event to add parent_event_id")
        print("-" * 80)
        
        # Create an orphan event first
        result = await handle_create_event(
            db,
            repos,
            {
                "event_type": "generic",
                "title": "Beach Day",
                "start_time": "2025-06-10T09:00:00",
                "end_time": "2025-06-10T18:00:00",
                "category": "entertainment",
                "location_id": str(location.id)
            }
        )
        orphan_event_data = json.loads(result[0].text)
        orphan_event_id = orphan_event_data["event_id"]
        print(f"✅ Created orphan event: {orphan_event_id}")
        
        # Now update it to have a parent
        result = await handle_update_event(
            db,
            repos,
            {
                "event_id": orphan_event_id,
                "parent_event_id": parent_event_id
            }
        )
        
        response_text = result[0].text
        print(response_text)
        update_data = json.loads(response_text)
        assert "error" not in update_data, f"Update failed: {update_data}"
        print(f"✅ TEST 3 PASSED: Event updated with parent_event_id")
        
        # Verify in database
        async with db.pool.acquire() as conn:
            orphan_row = await conn.fetchrow(
                "SELECT parent_event_id FROM events WHERE id = $1",
                UUID(orphan_event_id)
            )
            assert orphan_row['parent_event_id'] == UUID(parent_event_id), \
                f"Parent not set in update: expected {parent_event_id}, got {orphan_row['parent_event_id']}"
        
        print(f"✅ Database verified: orphan event now has parent_event_id = {parent_event_id}")
        
        # TEST 4: Remove parent_event_id by setting to null
        print()
        print("TEST 4: Remove parent_event_id by updating to null")
        print("-" * 80)
        
        result = await handle_update_event(
            db,
            repos,
            {
                "event_id": orphan_event_id,
                "parent_event_id": None
            }
        )
        
        response_text = result[0].text
        print(response_text)
        update_data = json.loads(response_text)
        assert "error" not in update_data, f"Update failed: {update_data}"
        print(f"✅ TEST 4 PASSED: Parent event ID removed")
        
        # Verify in database
        async with db.pool.acquire() as conn:
            orphan_row = await conn.fetchrow(
                "SELECT parent_event_id FROM events WHERE id = $1",
                UUID(orphan_event_id)
            )
            assert orphan_row['parent_event_id'] is None, \
                f"Parent should be null but is: {orphan_row['parent_event_id']}"
        
        print(f"✅ Database verified: event no longer has parent")
        
        # TEST 5: Query event hierarchy
        print()
        print("TEST 5: Query event hierarchy")
        print("-" * 80)
        
        async with db.pool.acquire() as conn:
            # Get all events in the trip
            hierarchy = await conn.fetch("""
                SELECT id, title, parent_event_id, 
                       CASE WHEN parent_event_id IS NOT NULL THEN 'child' ELSE 'top-level' END as role
                FROM events 
                WHERE id IN ($1, $2, $3)
                ORDER BY parent_event_id NULLS FIRST, title
            """, UUID(parent_event_id), UUID(child_event_id), UUID(orphan_event_id))
            
            print("Event Hierarchy:")
            for event in hierarchy:
                indent = "  " if event['role'] == 'child' else ""
                parent_info = f" (parent: {event['parent_event_id']})" if event['parent_event_id'] else ""
                print(f"{indent}├─ {event['title']}{parent_info}")
        
        print(f"✅ TEST 5 PASSED: Event hierarchy is queryable")
        
        print()
        print("=" * 80)
        print("✅ ALL TESTS PASSED!")
        print()
        print("Summary:")
        print("  - create_event accepts parent_event_id parameter")
        print("  - Child events are properly linked to parent events")
        print("  - update_event can set, update, and remove parent_event_id")
        print("  - Event hierarchy is queryable via parent_event_id foreign key")
        print("  - Issue #63 is resolved!")
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise


@pytest.mark.asyncio
async def test_create_event_with_parent_event_id(db):
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
