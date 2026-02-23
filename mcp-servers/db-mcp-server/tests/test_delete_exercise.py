"""
Test exercise deletion (Bug #78)

Tests for delete_exercise and undelete_exercise tools.
"""

import pytest
from uuid import UUID

from database import DatabaseConnection
from repositories import ExercisesRepository
from models import ExerciseCreate, ExerciseCategory


class TestExerciseDelete:
    """Test exercise deletion and restoration"""
    
    @pytest.mark.asyncio
    async def test_soft_delete_exercise(self, db_connection):
        """Verify exercise can be soft deleted"""
        db = db_connection
        exercises_repo = ExercisesRepository(db)
        
        # Create test exercise
        exercise = ExerciseCreate(
            canonical_name="Test Delete Exercise",
            category=ExerciseCategory.STRENGTH,
            primary_muscle_group="chest",
            secondary_muscle_groups=["triceps"],
            equipment=["barbell"],
            variants=[],
            notes="For testing deletion"
        )
        
        created = await exercises_repo.create(exercise)
        exercise_id = created.id
        
        # Verify it exists and is not deleted
        check_query = "SELECT is_deleted, deleted_at FROM exercises WHERE id = $1"
        result = await db.fetchrow(check_query, exercise_id)
        assert result['is_deleted'] is False
        assert result['deleted_at'] is None
        
        # Soft delete
        deleted = await exercises_repo.soft_delete(exercise_id)
        assert deleted['is_deleted'] is True
        assert deleted['deleted_at'] is not None
        
        # Verify deletion in database
        result = await db.fetchrow(check_query, exercise_id)
        assert result['is_deleted'] is True
        assert result['deleted_at'] is not None
    
    @pytest.mark.asyncio
    async def test_undelete_exercise(self, db_connection):
        """Verify deleted exercise can be restored"""
        db = db_connection
        exercises_repo = ExercisesRepository(db)
        
        # Create and delete exercise
        exercise = ExerciseCreate(
            canonical_name="Test Undelete Exercise",
            category=ExerciseCategory.CARDIO,
            primary_muscle_group="legs",
            secondary_muscle_groups=[],
            equipment=[],
            variants=[],
            notes="For testing undelete"
        )
        
        created = await exercises_repo.create(exercise)
        exercise_id = created.id
        
        # Delete it
        await exercises_repo.soft_delete(exercise_id)
        
        # Verify it's deleted
        check_query = "SELECT is_deleted, deleted_at FROM exercises WHERE id = $1"
        result = await db.fetchrow(check_query, exercise_id)
        assert result['is_deleted'] is True
        
        # Undelete
        restored = await exercises_repo.undelete(exercise_id)
        assert restored['is_deleted'] is False
        assert restored['deleted_at'] is None
        
        # Verify restoration in database
        result = await db.fetchrow(check_query, exercise_id)
        assert result['is_deleted'] is False
        assert result['deleted_at'] is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_exercise_raises_error(self, db_connection):
        """Verify deleting non-existent exercise raises error"""
        db = db_connection
        exercises_repo = ExercisesRepository(db)
        
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        
        with pytest.raises(ValueError) as exc_info:
            await exercises_repo.soft_delete(fake_id)
        
        assert "Exercise not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_undelete_nonexistent_exercise_raises_error(self, db_connection):
        """Verify undeleting non-existent exercise raises error"""
        db = db_connection
        exercises_repo = ExercisesRepository(db)
        
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        
        with pytest.raises(ValueError) as exc_info:
            await exercises_repo.undelete(fake_id)
        
        assert "Exercise not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_deleted_exercise_preserved_in_workout_history(self, db_connection, sample_data):
        """
        Verify deleted exercises are preserved for historical workout references.
        This is a soft delete - the record still exists in the database.
        """
        db = db_connection
        exercises_repo = ExercisesRepository(db)
        
        # Create exercise
        exercise_id = await sample_data.create_exercise("Historical Exercise")
        
        # Create workout using this exercise
        from repositories import WorkoutsRepository
        from models import EventCreate, EventType, Significance, WorkoutCreate, WorkoutCategory, WorkoutExercise, ExerciseSet, SetType
        from datetime import datetime
        
        workouts_repo = WorkoutsRepository(db)
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title="Test Workout",
            start_time=datetime.fromisoformat("2025-11-20T10:00:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        workout = WorkoutCreate(
            workout_name="Test",
            category=WorkoutCategory.STRENGTH,
            exercises=[
                WorkoutExercise(
                    exercise_id=exercise_id,
                    sequence_order=1,
                    sets=[
                        ExerciseSet(
                            set_number=1,
                            set_type=SetType.WORKING,
                            reps=10,
                            weight_kg=50.0
                        )
                    ]
                )
            ]
        )
        
        created_workout = await workouts_repo.create_with_event(event, workout)
        
        # Now delete the exercise
        await exercises_repo.soft_delete(exercise_id)
        
        # Verify workout still references the exercise (soft delete preserves data)
        workout_check = await workouts_repo.get_by_id(created_workout.workout.id)
        assert len(workout_check.exercises) == 1
        assert workout_check.exercises[0].exercise_id == exercise_id
        
        # Verify exercise record still exists (just marked as deleted)
        exercise_check = await db.fetchrow(
            "SELECT * FROM exercises WHERE id = $1",
            exercise_id
        )
        assert exercise_check is not None
        assert exercise_check['is_deleted'] is True
        assert exercise_check['canonical_name'] == "Historical Exercise"
