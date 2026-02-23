#!/usr/bin/env python3
"""
Quick test to verify delete_workout and undelete_workout handlers work correctly.
"""
import asyncio
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseConnection
from config import DatabaseConfig
from repositories import (
    PeopleRepository, LocationsRepository, ExercisesRepository,
    WorkoutsRepository, EventsRepository
)
from models import (
    EventCreate, EventType, WorkoutCreate, WorkoutCategory, 
    WorkoutExercise, ExerciseSet, SetType, Significance,
    ExerciseCreate, ExerciseCategory
)
from handlers.workout_handlers import handle_delete_workout, handle_undelete_workout
from datetime import datetime, timedelta


class RepositoryContainer:
    def __init__(self, db):
        self.people = PeopleRepository(db)
        self.locations = LocationsRepository(db)
        self.exercises = ExercisesRepository(db)
        self.workouts = WorkoutsRepository(db)
        self.events = EventsRepository(db)


async def run_test_logic(db):
    """Test deleting and undeleting a workout"""
    
    repos = RepositoryContainer(db)
    
    # Create a location
    location = await repos.locations.get_or_create("Test Gym")
    
    # Create an exercise with unique name
    import uuid
    exercise_name = f"Test Exercise {uuid.uuid4()}"
    exercise = await repos.exercises.create(
        ExerciseCreate(
            canonical_name=exercise_name,
            category=ExerciseCategory.STRENGTH,
            primary_muscle_group="chest"
        )
    )
    
    # Create an event
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=1)
    
    event = EventCreate(
        event_type=EventType.WORKOUT,
        title="Test Workout",
        start_time=start_time,
        end_time=end_time,
        location_id=location.id,
        significance=Significance.ROUTINE
    )
    
    # Create a workout
    workout = WorkoutCreate(
        workout_name="Push Day",
        category=WorkoutCategory.STRENGTH,
        exercises=[
            WorkoutExercise(
                exercise_id=exercise.id,
                sequence_order=1,
                sets=[
                    ExerciseSet(
                        set_number=1,
                        set_type=SetType.WARMUP,
                        weight_kg=60,
                        reps=10
                    ),
                    ExerciseSet(
                        set_number=2,
                        set_type=SetType.WORKING,
                        weight_kg=80,
                        reps=8
                    )
                ]
            )
        ]
    )
    
    # Create the workout
    created = await repos.workouts.create_with_event(event, workout)
    event_id = str(created.event.id)
    
    print(f"[OK] Created workout event: {event_id}")
    print(f"   Title: {created.event.title}")
    print(f"   Start time: {created.event.start_time}")
    
    # Test delete
    delete_result = await handle_delete_workout(db, {"event_id": event_id})
    print(f"\n[OK] Delete result: {delete_result[0].text}")
    
    # Verify it's deleted (soft delete)
    query = "SELECT is_deleted, deleted_at FROM events WHERE id = $1"
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, created.event.id)
        assert row['is_deleted'] == True, "Event should be marked as deleted"
        assert row['deleted_at'] is not None, "deleted_at should be set"
    print(f"[OK] Verified event is soft-deleted")
    
    # Test undelete
    undelete_result = await handle_undelete_workout(db, {"event_id": event_id})
    print(f"[OK] Undelete result: {undelete_result[0].text}")
    
    # Verify it's restored
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, created.event.id)
        assert row['is_deleted'] == False, "Event should no longer be deleted"
        assert row['deleted_at'] is None, "deleted_at should be NULL"
    print(f"[OK] Verified event is restored")
    
    print("\n[OK] All tests passed!")


@pytest.mark.asyncio
async def test_delete_undelete_workout(db):
    await run_test_logic(db)


if __name__ == "__main__":
    async def main():
        # Setup database - FORCE TEST MODE
        config = DatabaseConfig.from_environment('test')
        db = DatabaseConnection(config)
        await db.connect()
        try:
            await run_test_logic(db)
        finally:
            await db.disconnect()

    asyncio.run(main())
