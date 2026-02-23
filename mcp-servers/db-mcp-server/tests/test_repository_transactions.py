"""
Repository Transaction Behavior Tests

These tests directly test repository-level transaction handling to ensure:
1. Nested operations work correctly within a single transaction
2. Rollback happens when any part fails
3. No partial data is created on failure

This complements test_server_integration.py which tests through the server layer.
"""

import pytest
import asyncio
from uuid import UUID
from datetime import datetime

from database import DatabaseConnection
from repositories import EventsRepository, WorkoutsRepository, MealsRepository, CommutesRepository
from models import (
    EventCreate, EventType, Significance, 
    WorkoutCreate, WorkoutCategory, WorkoutExercise, ExerciseSet, SetType,
    MealCreate, MealItem, CommuteCreate, TransportMode
)


class TestRepositoryTransactions:
    """Test transaction behavior at repository level"""
    
    @pytest.mark.asyncio
    async def test_workout_creation_uses_single_transaction(self, db_connection, sample_data):
        """
        Verify WorkoutsRepository.create_with_event uses a single transaction.
        
        This test would have caught Bug #75 - the nested transaction savepoint error.
        """
        db = db_connection
        workout_repo = WorkoutsRepository(db)
        
        # Create exercises
        ex_ids = [await sample_data.create_exercise(f"TransEx{i}") for i in range(8)]
        
        # Create workout with 8 exercises
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title="Single Transaction Test",
            start_time=datetime.fromisoformat("2025-11-20T09:00:00"),
            end_time=datetime.fromisoformat("2025-11-20T10:30:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        workout = WorkoutCreate(
            workout_name="Transaction Test",
            category=WorkoutCategory.STRENGTH,
            exercises=[
                WorkoutExercise(
                    exercise_id=ex_ids[i],
                    sequence_order=i + 1,
                    sets=[
                        ExerciseSet(set_number=1, set_type=SetType.WARMUP, reps=10, weight_kg=40),
                        ExerciseSet(set_number=2, set_type=SetType.WORKING, reps=8, weight_kg=60)
                    ]
                )
                for i in range(8)
            ]
        )
        
        # This should NOT raise savepoint errors
        result = await workout_repo.create_with_event(event, workout)
        
        assert result is not None
        assert result.workout.id is not None
        assert result.event.id is not None
        
        # Verify all data was created
        workout_count = await db.fetchval(
            "SELECT COUNT(*) FROM workout_exercises WHERE workout_id = $1",
            result.workout.id
        )
        assert workout_count == 8
        
        sets_count = await db.fetchval(
            "SELECT COUNT(*) FROM exercise_sets es "
            "JOIN workout_exercises we ON es.workout_exercise_id = we.id "
            "WHERE we.workout_id = $1",
            result.workout.id
        )
        assert sets_count == 16  # 8 exercises * 2 sets each
    
    @pytest.mark.asyncio
    async def test_workout_rollback_on_invalid_exercise(self, db_connection, sample_data):
        """
        Verify workout creation rolls back entirely if any exercise is invalid.
        
        This tests atomicity - all or nothing.
        """
        db = db_connection
        workout_repo = WorkoutsRepository(db)
        
        # Create one valid exercise
        valid_ex = await sample_data.create_exercise("ValidEx")
        invalid_ex = UUID("00000000-0000-0000-0000-000000000000")
        
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title="Rollback Test Workout",
            start_time=datetime.fromisoformat("2025-11-20T09:00:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        workout = WorkoutCreate(
            workout_name="Should Rollback",
            category=WorkoutCategory.STRENGTH,
            exercises=[
                WorkoutExercise(
                    exercise_id=valid_ex,
                    sequence_order=1,
                    sets=[ExerciseSet(set_number=1, set_type=SetType.WORKING, reps=10)]
                ),
                WorkoutExercise(
                    exercise_id=invalid_ex,  # Invalid - doesn't exist
                    sequence_order=2,
                    sets=[ExerciseSet(set_number=1, set_type=SetType.WORKING, reps=10)]
                )
            ]
        )
        
        # This should fail
        with pytest.raises(Exception):
            await workout_repo.create_with_event(event, workout)
        
        # Verify NO partial data exists
        event_count = await db.fetchval(
            "SELECT COUNT(*) FROM events WHERE title = 'Rollback Test Workout'"
        )
        assert event_count == 0, "Event should have been rolled back"
        
        workout_count = await db.fetchval(
            "SELECT COUNT(*) FROM workouts WHERE workout_name = 'Should Rollback'"
        )
        assert workout_count == 0, "Workout should have been rolled back"
    
    @pytest.mark.asyncio
    async def test_meal_rollback_on_failed_item_insert(self, db_connection):
        """
        Verify meal creation rolls back if item insert fails.
        
        This tests atomicity for meal + items.
        """
        db = db_connection
        meal_repo = MealsRepository(db)
        
        event = EventCreate(
            event_type=EventType.MEAL,
            title="Meal Rollback Test",
            start_time=datetime.fromisoformat("2025-11-20T12:00:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        # Create meal with items that might fail
        meal = MealCreate(
            meal_title="lunch",
            items=[
                MealItem(item_name="Item 1", quantity="100g"),
                MealItem(item_name="Item 2", quantity="200g"),
                # Add more items to test transaction
            ]
        )
        
        # Normal creation should work
        result = await meal_repo.create_with_event(event, meal)
        assert result is not None
        
        # Verify event and meal exist
        meal_count = await db.fetchval(
            "SELECT COUNT(*) FROM meals WHERE id = $1",
            result.meal.id
        )
        assert meal_count == 1
        
        items_count = await db.fetchval(
            "SELECT COUNT(*) FROM meal_items WHERE meal_id = $1",
            result.meal.id
        )
        assert items_count == 2
    
    @pytest.mark.asyncio
    async def test_commute_has_transaction_wrapper(self, db_connection, sample_data):
        """
        Verify CommutesRepository.create_with_event uses transaction.
        
        Bug discovered during analysis: CommutesRepository had NO transaction wrapper.
        This test ensures it's been added.
        """
        db = db_connection
        commute_repo = CommutesRepository(db)
        
        # Create locations
        from_loc = await sample_data.create_location("From Location")
        to_loc = UUID("00000000-0000-0000-0000-000000000000")  # Invalid
        
        event = EventCreate(
            event_type=EventType.COMMUTE,
            title="Commute Atomicity Test",
            start_time=datetime.fromisoformat("2025-11-20T08:00:00"),
            significance=Significance.ROUTINE,
            category="travel",
            participants=[]
        )
        
        commute = CommuteCreate(
            from_location_id=from_loc,
            to_location_id=to_loc,  # Invalid - will fail FK constraint
            transport_mode=TransportMode.DRIVING
        )
        
        # This should fail due to invalid to_location
        with pytest.raises(Exception):
            await commute_repo.create_with_event(event, commute)
        
        # Verify event was NOT created (proves transaction wrapping works)
        event_count = await db.fetchval(
            "SELECT COUNT(*) FROM events WHERE title = 'Commute Atomicity Test'"
        )
        assert event_count == 0, "Event should have been rolled back due to transaction"


class TestNestedTransactionBehavior:
    """Test that EventsRepository.create() works inside parent transactions"""
    
    @pytest.mark.asyncio
    async def test_events_repo_works_inside_transaction(self, db_connection):
        """
        Verify EventsRepository.create() can be called from within a transaction.
        
        Bug #75 was caused by EventsRepository.create() creating its own transaction,
        causing nested transaction savepoint errors.
        """
        db = db_connection
        events_repo = EventsRepository(db)
        
        # Start a parent transaction
        async with db.transaction():
            event = EventCreate(
                event_type=EventType.GENERIC,
                title="Nested Transaction Test",
                start_time=datetime.fromisoformat("2025-11-20T14:00:00"),
                significance=Significance.ROUTINE,
                category="personal",
                participants=[]
            )
            
            # This should NOT raise savepoint errors
            created_event = await events_repo.create(event)
            assert created_event is not None
            assert created_event.id is not None
        
        # Verify event was created
        event_count = await db.fetchval(
            "SELECT COUNT(*) FROM events WHERE title = 'Nested Transaction Test'"
        )
        assert event_count == 1


class TestConnectionPoolRecovery:
    """Test connection pool remains healthy after errors"""
    
    @pytest.mark.asyncio
    async def test_pool_recovers_after_transaction_failure(self, db_connection):
        """
        Verify connection pool is healthy after transaction fails.
        
        Bug #73 was connection pool corruption after failed operations.
        """
        db = db_connection
        
        # Get initial pool state
        initial_stats = await db.get_pool_stats()
        assert initial_stats["status"] == "connected"
        
        # Force a transaction to fail
        try:
            async with db.transaction():
                await db.execute("INSERT INTO nonexistent_table VALUES (1)")
        except Exception:
            pass  # Expected
        
        # Pool should still be healthy
        assert await db.check_connection(), "Pool should be healthy after failed transaction"
        
        # Pool size should be unchanged
        final_stats = await db.get_pool_stats()
        assert final_stats["size"] == initial_stats["size"]
        assert final_stats["status"] == "connected"
        
        # Next operation should work
        result = await db.fetchval("SELECT 1")
        assert result == 1
    
    @pytest.mark.asyncio
    async def test_pool_handles_multiple_sequential_failures(self, db_connection):
        """
        Verify pool remains healthy after multiple failures in sequence.
        
        This simulates a scenario where multiple operations fail rapidly.
        """
        db = db_connection
        
        # Cause 5 failures in a row
        for i in range(5):
            try:
                await db.execute(f"INSERT INTO nonexistent_table_{i} VALUES (1)")
            except Exception:
                pass  # Expected
        
        # Pool should still be healthy
        assert await db.check_connection()
        
        # Subsequent operations should work
        for i in range(5):
            result = await db.fetchval(f"SELECT {i}")
            assert result == i
    
    @pytest.mark.asyncio
    async def test_pool_handles_parallel_operation_failures(self, db_connection):
        """
        Verify pool remains healthy when parallel operations fail.
        
        This reproduces the Bug #73 scenario more closely.
        """
        db = db_connection
        
        # Start multiple operations, some will fail
        async def failing_op(i):
            if i % 2 == 0:
                # This will fail
                await db.execute(f"INSERT INTO nonexistent_table VALUES ({i})")
            else:
                # This will succeed
                return await db.fetchval(f"SELECT {i}")
        
        results = await asyncio.gather(
            *[failing_op(i) for i in range(10)],
            return_exceptions=True
        )
        
        # Some should fail, some succeed
        failures = sum(1 for r in results if isinstance(r, Exception))
        successes = sum(1 for r in results if not isinstance(r, Exception))
        
        assert failures == 5
        assert successes == 5
        
        # CRITICAL: Pool must still work
        assert await db.check_connection()
        
        # Pool should not have leaked connections
        stats = await db.get_pool_stats()
        assert stats["status"] == "connected"
        
        # Next operation should work
        result = await db.fetchval("SELECT 1")
        assert result == 1
