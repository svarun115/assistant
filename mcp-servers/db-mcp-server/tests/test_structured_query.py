"""
Integration tests for the structured query language (QUERY_MODE=structured).

Tests run against the test database (assistant_test) with real data.
Verifies: query tool, aggregate tool, cross-entity filters, date shorthand,
relationship hydration, soft-delete filtering, validation errors.
"""

import os
import json
import pytest
from uuid import UUID

# Force structured query mode for handler registration
os.environ['QUERY_MODE'] = 'structured'

from handlers.query_handlers import handle_query, handle_aggregate


# ============================================================================
# Fixtures for inserting test data
# ============================================================================

@pytest.fixture
async def seeded_db(db_connection, sample_data):
    """
    Seed the test database with a variety of entities for query testing.
    Returns a dict of created IDs for assertions.
    """
    db = db_connection
    ids = {}

    # People
    ids["person_gauri"] = await sample_data.create_person("Gauri Sharma")
    ids["person_mohit"] = await sample_data.create_person("Mohit Patel")

    # Locations
    ids["loc_gym"] = await sample_data.create_location("Gold's Gym", location_type="gym")
    ids["loc_cafe"] = await sample_data.create_location("Third Wave Coffee", location_type="restaurant")

    # Exercises
    ids["exercise_bench"] = await sample_data.create_exercise("Bench Press")
    ids["exercise_squat"] = await sample_data.create_exercise("Squat")

    # Events with participants
    async with db.pool.acquire() as conn:
        # Event 1: Meal with Gauri (Jan 15)
        row = await conn.fetchrow("""
            INSERT INTO events (event_type, title, start_time, end_time, location_id, category, tags)
            VALUES ('generic', 'Lunch with Gauri', '2026-01-15T12:30:00', '2026-01-15T13:30:00', $1, 'social', ARRAY['food','social'])
            RETURNING id
        """, ids["loc_cafe"])
        ids["event_lunch"] = row["id"]

        await conn.execute("""
            INSERT INTO event_participants (event_id, person_id, role)
            VALUES ($1, $2, 'friend')
        """, ids["event_lunch"], ids["person_gauri"])

        # Event 2: Workout (Jan 20)
        row = await conn.fetchrow("""
            INSERT INTO events (event_type, title, start_time, end_time, location_id, category)
            VALUES ('generic', 'Morning Workout', '2026-01-20T07:00:00', '2026-01-20T08:30:00', $1, 'health')
            RETURNING id
        """, ids["loc_gym"])
        ids["event_workout"] = row["id"]

        await conn.execute("""
            INSERT INTO event_participants (event_id, person_id, role)
            VALUES ($1, $2, 'partner')
        """, ids["event_workout"], ids["person_mohit"])

        # Event 3: Solo event in Feb
        row = await conn.fetchrow("""
            INSERT INTO events (event_type, title, start_time, category)
            VALUES ('generic', 'Solo Reading', '2026-02-05T20:00:00', 'personal')
            RETURNING id
        """)
        ids["event_solo"] = row["id"]

        # Event 4: Soft-deleted event (should never appear)
        row = await conn.fetchrow("""
            INSERT INTO events (event_type, title, start_time, category, is_deleted, deleted_at)
            VALUES ('generic', 'DELETED EVENT', '2026-01-18T10:00:00', 'work', TRUE, NOW())
            RETURNING id
        """)
        ids["event_deleted"] = row["id"]

        # Workout specialization
        row = await conn.fetchrow("""
            INSERT INTO workouts (event_id, workout_name, category)
            VALUES ($1, 'Push Day', 'STRENGTH')
            RETURNING id
        """, ids["event_workout"])
        ids["workout_id"] = row["id"]

        # Workout exercises + sets
        row = await conn.fetchrow("""
            INSERT INTO workout_exercises (workout_id, exercise_id, sequence_order)
            VALUES ($1, $2, 1)
            RETURNING id
        """, ids["workout_id"], ids["exercise_bench"])
        we_id = row["id"]

        await conn.execute("""
            INSERT INTO exercise_sets (workout_exercise_id, set_number, set_type, weight_kg, reps)
            VALUES ($1, 1, 'WARMUP', 60, 10), ($1, 2, 'WORKING', 100, 8)
        """, we_id)

        # Meal specialization
        row = await conn.fetchrow("""
            INSERT INTO meals (event_id, meal_title, meal_type)
            VALUES ($1, 'lunch', 'restaurant')
            RETURNING id
        """, ids["event_lunch"])
        ids["meal_id"] = row["id"]

        await conn.execute("""
            INSERT INTO meal_items (meal_id, item_name, quantity)
            VALUES ($1, 'Pasta Carbonara', '1 plate'), ($1, 'Iced Latte', '1 glass')
        """, ids["meal_id"])

        # Journal entry
        row = await conn.fetchrow("""
            INSERT INTO journal_entries (entry_date, entry_type, raw_text, tags)
            VALUES ('2026-01-15', 'journal', 'Had a great lunch with Gauri today', ARRAY['social','food'])
            RETURNING id
        """)
        ids["journal_id"] = row["id"]

    return ids


# ============================================================================
# Query Tool Tests
# ============================================================================

class TestQueryBasic:
    """Basic query functionality."""

    @pytest.mark.asyncio
    async def test_query_all_events(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {"entity": "events"}))[0].text
        result = json.loads(result_text)

        assert result["entity"] == "events"
        assert result["count"] == 3  # 3 non-deleted events
        assert result["total"] == 3
        # Deleted event must not appear
        titles = [r["title"] for r in result["results"]]
        assert "DELETED EVENT" not in titles

    @pytest.mark.asyncio
    async def test_query_events_with_filter(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"category": {"eq": "social"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        assert result["results"][0]["title"] == "Lunch with Gauri"

    @pytest.mark.asyncio
    async def test_query_people(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {"entity": "people"}))[0].text
        result = json.loads(result_text)

        assert result["count"] == 2
        names = {r["name"] for r in result["results"]}
        assert names == {"Gauri Sharma", "Mohit Patel"}

    @pytest.mark.asyncio
    async def test_query_pagination(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "limit": 1,
            "offset": 0,
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        assert result["total"] == 3
        assert result["hasMore"] is True

    @pytest.mark.asyncio
    async def test_query_ordering(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "orderBy": "start",
            "orderDir": "asc",
        }))[0].text
        result = json.loads(result_text)

        dates = [r["start"] for r in result["results"]]
        assert dates == sorted(dates)


class TestQueryDateShorthand:
    """Date range shorthand expansion."""

    @pytest.mark.asyncio
    async def test_date_month_shorthand(self, db_connection, seeded_db):
        """date eq '2026-01' should return only January events."""
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"date": {"eq": "2026-01"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 2  # lunch + workout (both in Jan, deleted excluded)
        for r in result["results"]:
            assert r["date"].startswith("2026-01")

    @pytest.mark.asyncio
    async def test_date_gte_month(self, db_connection, seeded_db):
        """date gte '2026-02' should return only Feb+ events."""
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"date": {"gte": "2026-02"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        assert result["results"][0]["title"] == "Solo Reading"


class TestQueryCrossEntity:
    """Cross-entity dot-notation filters."""

    @pytest.mark.asyncio
    async def test_filter_events_by_participant_name(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"participants.name": {"contains": "Gauri"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        assert result["results"][0]["title"] == "Lunch with Gauri"

    @pytest.mark.asyncio
    async def test_filter_events_by_location_name(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"location.name": {"contains": "Gold"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        assert result["results"][0]["title"] == "Morning Workout"


class TestQueryIncludes:
    """Relationship hydration via include."""

    @pytest.mark.asyncio
    async def test_include_participants(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"title": {"contains": "Lunch"}},
            "include": ["participants"],
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        event = result["results"][0]
        assert "participants" in event
        assert len(event["participants"]) == 1
        assert event["participants"][0]["canonical_name"] == "Gauri Sharma"

    @pytest.mark.asyncio
    async def test_include_location(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"title": {"contains": "Workout"}},
            "include": ["location"],
        }))[0].text
        result = json.loads(result_text)

        event = result["results"][0]
        assert event["location"] is not None
        assert event["location"]["canonical_name"] == "Gold's Gym"

    @pytest.mark.asyncio
    async def test_include_meal_items(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "meals",
            "include": ["items"],
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        meal = result["results"][0]
        assert "items" in meal
        assert len(meal["items"]) == 2
        item_names = {i["item_name"] for i in meal["items"]}
        assert "Pasta Carbonara" in item_names

    @pytest.mark.asyncio
    async def test_include_workout_exercises(self, db_connection, seeded_db):
        result_text = (await handle_query(db_connection, {
            "entity": "workouts",
            "include": ["exercises"],
        }))[0].text
        result = json.loads(result_text)

        assert result["count"] == 1
        workout = result["results"][0]
        assert "exercises" in workout
        assert len(workout["exercises"]) == 1


# ============================================================================
# Aggregate Tool Tests
# ============================================================================

class TestAggregate:

    @pytest.mark.asyncio
    async def test_count_all_events(self, db_connection, seeded_db):
        result_text = (await handle_aggregate(db_connection, {
            "entity": "events",
            "aggregate": {"count": True},
        }))[0].text
        result = json.loads(result_text)

        assert result["aggregation"] is True
        assert result["results"][0]["count"] == 3

    @pytest.mark.asyncio
    async def test_count_by_category(self, db_connection, seeded_db):
        result_text = (await handle_aggregate(db_connection, {
            "entity": "events",
            "aggregate": {"count": True},
            "groupBy": ["category"],
        }))[0].text
        result = json.loads(result_text)

        category_counts = {r["category"]: r["count"] for r in result["results"]}
        assert category_counts.get("social") == 1
        assert category_counts.get("health") == 1
        assert category_counts.get("personal") == 1
        assert "work" not in category_counts  # deleted event excluded

    @pytest.mark.asyncio
    async def test_aggregate_duration(self, db_connection, seeded_db):
        result_text = (await handle_aggregate(db_connection, {
            "entity": "events",
            "where": {"duration": {"isNull": False}},
            "aggregate": {"avg": "duration", "max": "duration"},
        }))[0].text
        result = json.loads(result_text)

        assert "avg" in result["results"][0]
        assert "max" in result["results"][0]


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:

    @pytest.mark.asyncio
    async def test_unknown_entity(self, db_connection):
        result_text = (await handle_query(db_connection, {"entity": "foo"}))[0].text
        result = json.loads(result_text)

        assert result["error"] is True
        assert result["errors"][0]["code"] == "UNKNOWN_ENTITY"
        assert "validEntities" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_unknown_field(self, db_connection):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"bad_field": {"eq": "x"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["error"] is True
        assert result["errors"][0]["code"] == "UNKNOWN_FIELD"

    @pytest.mark.asyncio
    async def test_invalid_dot_notation(self, db_connection):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "where": {"badrel.name": {"eq": "x"}},
        }))[0].text
        result = json.loads(result_text)

        assert result["error"] is True
        assert result["errors"][0]["code"] == "INVALID_RELATIONSHIP"

    @pytest.mark.asyncio
    async def test_invalid_include(self, db_connection):
        result_text = (await handle_query(db_connection, {
            "entity": "events",
            "include": ["nonexistent"],
        }))[0].text
        result = json.loads(result_text)

        assert result["error"] is True
        assert result["errors"][0]["code"] == "INVALID_RELATIONSHIP"


# ============================================================================
# Soft-Delete Tests
# ============================================================================

class TestSoftDelete:

    @pytest.mark.asyncio
    async def test_deleted_events_never_returned(self, db_connection, seeded_db):
        """Soft-deleted events must never appear in results."""
        result_text = (await handle_query(db_connection, {"entity": "events", "limit": 200}))[0].text
        result = json.loads(result_text)

        for r in result["results"]:
            assert r["title"] != "DELETED EVENT"

    @pytest.mark.asyncio
    async def test_deleted_events_excluded_from_count(self, db_connection, seeded_db):
        result_text = (await handle_aggregate(db_connection, {
            "entity": "events",
            "aggregate": {"count": True},
        }))[0].text
        result = json.loads(result_text)

        assert result["results"][0]["count"] == 3  # Not 4
