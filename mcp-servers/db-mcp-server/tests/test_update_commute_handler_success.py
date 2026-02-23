import json
from datetime import datetime
from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_update_commute_updates_event_and_route(db, repos):
    from handlers.travel_handlers import handle_create_commute, handle_update_commute

    from_location = await repos.locations.get_or_create("Soft Serve Company")
    to_location = await repos.locations.get_or_create("Home")

    # Create commute
    create_args = {
        "event": {
            "title": "Drive home",
            "start_time": "2025-09-15T22:30:00",
            "end_time": "2025-09-15T23:20:00",
            "notes": "Initial",
            "tags": ["commute"],
            "category": "travel",
        },
        "commute": {
            "from_location_id": str(from_location.id),
            "to_location_id": str(to_location.id),
            "transport_mode": "driving",
        },
    }

    create_result = await handle_create_commute(db, repos, create_args)
    payload = json.loads(create_result[0].text)
    commute_id = UUID(payload["commute_id"])

    # Create/resolve locations to update to
    office = await repos.locations.get_or_create("Office")
    gym = await repos.locations.get_or_create("Gym")

    update_args = {
        "commute_id": str(commute_id),
        "title": "Drive back home (dropped Ranju)",
        "start_time": "2025-09-15T22:35:00",
        "end_time": "2025-09-15T23:15:00",
        "from_location_id": str(office.id),
        "to_location_id": str(gym.id),
        "notes": "Updated notes",
        "transport_mode": "driving",
    }

    update_result = await handle_update_commute(db, repos, update_args)
    update_payload = json.loads(update_result[0].text)
    assert update_payload.get("commute_id") == str(commute_id)

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM commute_events WHERE commute_id = $1",
            commute_id,
        )

    assert row is not None
    assert row["event_title"] == "Drive back home (dropped Ranju)"
    assert row["event_notes"] == "Updated notes"
    assert row["start_time"] == datetime.fromisoformat("2025-09-15T22:35:00")
    assert row["end_time"] == datetime.fromisoformat("2025-09-15T23:15:00")
    assert row["from_location_id"] == office.id
    assert row["to_location_id"] == gym.id
    assert row["transport_mode"] == "driving"
