"""
Test sleep event creation and sleep_events VIEW functionality
Addresses Issue #68
"""

import pytest
from datetime import datetime
from uuid import UUID


@pytest.mark.asyncio
async def test_create_sleep_event_populates_view(db, repos):
    """Test that creating a sleep event makes it visible in sleep_events VIEW"""
    
    # Create a sleep event
    from handlers.event_handlers import handle_create_event
    
    arguments = {
        "event_type": "sleep",
        "start_time": "2025-06-25T01:15:00",
        "end_time": "2025-06-25T06:30:00",
        "quality": "fair",
        "dream_recall": False,
        "interruptions": 0
    }
    
    result = await handle_create_event(db, repos, arguments)
    
    # Extract event_id from result
    import json
    result_data = json.loads(result[0].text)
    assert "event_id" in result_data
    event_id = result_data["event_id"]
    
    # Query sleep_events VIEW
    query = """
        SELECT * FROM sleep_events 
        WHERE event_id = $1
    """
    
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, UUID(event_id))
    
    # Verify the VIEW returns the sleep event
    assert row is not None, "Sleep event should be visible in sleep_events VIEW"
    assert str(row["event_id"]) == event_id
    assert row["sleep_time"] == datetime.fromisoformat("2025-06-25T01:15:00")
    assert row["wake_time"] == datetime.fromisoformat("2025-06-25T06:30:00")
    
    # Verify duration calculation
    expected_duration_hours = 5.25  # 5 hours 15 minutes
    assert abs(float(row["duration_hours"]) - expected_duration_hours) < 0.1


@pytest.mark.asyncio
async def test_sleep_events_view_filters_correctly(db, repos):
    """Test that sleep_events VIEW only shows events with event_type='sleep'"""
    
    from handlers.event_handlers import handle_create_event
    
    # Create a sleep event
    sleep_args = {
        "event_type": "sleep",
        "start_time": "2025-06-25T01:00:00",
        "end_time": "2025-06-25T07:00:00"
    }
    sleep_result = await handle_create_event(db, repos, sleep_args)
    import json
    sleep_event_id = json.loads(sleep_result[0].text)["event_id"]
    
    # Create a generic event with 'sleep' in title (should NOT appear in VIEW)
    generic_args = {
        "event_type": "generic",
        "title": "Can't sleep - reading",
        "start_time": "2025-06-25T02:00:00",
        "tags": ["sleep", "reading"]
    }
    generic_result = await handle_create_event(db, repos, generic_args)
    generic_event_id = json.loads(generic_result[0].text)["event_id"]
    
    # Query sleep_events VIEW
    query = "SELECT event_id FROM sleep_events WHERE event_id = ANY($1::uuid[])"
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, [UUID(sleep_event_id), UUID(generic_event_id)])
    
    event_ids = [str(row["event_id"]) for row in rows]
    
    # Only the sleep event should be in the VIEW
    assert sleep_event_id in event_ids, "Sleep event should be in VIEW"
    assert generic_event_id not in event_ids, "Generic event with 'sleep' tag should NOT be in VIEW"


@pytest.mark.asyncio
async def test_sleep_event_notes_contain_quality_info(db, repos):
    """Test that sleep-specific fields are stored in notes"""
    
    from handlers.event_handlers import handle_create_event
    
    arguments = {
        "event_type": "sleep",
        "start_time": "2025-06-25T01:00:00",
        "end_time": "2025-06-25T07:00:00",
        "quality": "excellent",
        "dream_recall": True,
        "interruptions": 2,
        "notes": "Had vivid dreams"
    }
    
    result = await handle_create_event(db, repos, arguments)
    
    import json
    result_data = json.loads(result[0].text)
    event_id = result_data["event_id"]
    
    # Query the event to check notes
    query = "SELECT notes FROM events WHERE id = $1"
    
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, UUID(event_id))
    
    notes = row["notes"]
    
    # Verify sleep-specific fields are in notes
    assert "Quality: excellent" in notes
    assert "Interruptions: 2" in notes
    assert "Dream recall: Yes" in notes
    assert "Had vivid dreams" in notes


@pytest.mark.asyncio
async def test_update_sleep_event_updates_notes(db, repos):
    """Test that updating sleep event updates the notes field"""
    
    from handlers.event_handlers import handle_create_event, handle_update_event
    
    # Create sleep event
    create_args = {
        "event_type": "sleep",
        "start_time": "2025-06-25T01:00:00",
        "end_time": "2025-06-25T07:00:00",
        "quality": "fair"
    }
    
    result = await handle_create_event(db, repos, create_args)
    
    import json
    event_id = json.loads(result[0].text)["event_id"]
    
    # Update sleep quality
    update_args = {
        "event_id": event_id,
        "event_type": "sleep",
        "quality": "excellent",
        "interruptions": 0,
        "dream_recall": True
    }
    
    await handle_update_event(db, repos, update_args)
    
    # Verify notes were updated
    query = "SELECT notes FROM events WHERE id = $1"
    
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, UUID(event_id))
    
    notes = row["notes"]
    
    assert "Quality: excellent" in notes
    assert "Interruptions: 0" in notes
    assert "Dream recall: Yes" in notes


@pytest.mark.asyncio
async def test_update_sleep_event_updates_end_time_persists(db, repos):
    """Regression: updating sleep end_time must persist (Issue #94)."""

    from handlers.event_handlers import handle_create_event, handle_update_event

    # Create sleep event without an end_time
    create_args = {
        "event_type": "sleep",
        "start_time": "2025-09-04T02:00:00",
        "notes": "Initial sleep block"
    }
    result = await handle_create_event(db, repos, create_args)

    import json
    event_id = json.loads(result[0].text)["event_id"]

    # Update end_time
    update_args = {
        "event_id": event_id,
        "event_type": "sleep",
        "end_time": "2025-09-04T09:00:00",
        "notes": "Woke up at 9"
    }
    await handle_update_event(db, repos, update_args)

    async with db.pool.acquire() as conn:
        event_row = await conn.fetchrow(
            "SELECT start_time, end_time FROM events WHERE id = $1",
            UUID(event_id),
        )
        assert event_row is not None
        assert event_row["start_time"] == datetime.fromisoformat("2025-09-04T02:00:00")
        assert event_row["end_time"] == datetime.fromisoformat("2025-09-04T09:00:00")

        sleep_row = await conn.fetchrow(
            "SELECT sleep_time, wake_time FROM sleep_events WHERE event_id = $1",
            UUID(event_id),
        )
        assert sleep_row is not None
        assert sleep_row["sleep_time"] == datetime.fromisoformat("2025-09-04T02:00:00")
        assert sleep_row["wake_time"] == datetime.fromisoformat("2025-09-04T09:00:00")
