"""
Test for Bug #77: interval_description field missing from ExerciseSet model

This test verifies that interval-based workouts (Tabata, HIIT, time-based exercises)
can be created with interval_description instead of reps.
"""

import pytest
from datetime import datetime
from uuid import UUID

from database import DatabaseConnection
from repositories import WorkoutsRepository
from models import (
    EventCreate, EventType, Significance,
    WorkoutCreate, WorkoutCategory, WorkoutExercise, ExerciseSet, SetType
)


class TestIntervalDescriptionField:
    """Test interval_description field is properly supported"""
    
    @pytest.mark.asyncio
    async def test_workout_with_interval_description_no_reps(self, db_connection, sample_data):
        """
        Verify workout can be created with interval_description and NULL reps.
        
        Bug #77: Previously failed with constraint violation because interval_description
        was stripped by the model, leaving both reps and interval_description as NULL.
        """
        db = db_connection
        workout_repo = WorkoutsRepository(db)
        
        # Create a Tabata exercise
        tabata_ex = await sample_data.create_exercise("Tabata Burpees")
        
        # Create event
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title="Tabata HIIT Session",
            start_time=datetime.fromisoformat("2025-11-20T07:00:00"),
            end_time=datetime.fromisoformat("2025-11-20T07:20:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        # Create workout with interval-based sets (NO reps, NO distance)
        workout = WorkoutCreate(
            workout_name="Tabata Morning Session",
            category=WorkoutCategory.CARDIO,
            exercises=[
                WorkoutExercise(
                    exercise_id=tabata_ex,
                    sequence_order=1,
                    sets=[
                        # Set 1: Pure interval description, no reps
                        ExerciseSet(
                            set_number=1,
                            set_type=SetType.WORKING,
                            interval_description="20s work, 10s rest",
                            work_duration_s=20,
                            rest_duration_s=10,
                            reps=None,  # Explicitly NULL
                            weight_kg=None
                        ),
                        # Set 2: Another interval
                        ExerciseSet(
                            set_number=2,
                            set_type=SetType.WORKING,
                            interval_description="20s work, 10s rest",
                            work_duration_s=20,
                            rest_duration_s=10
                        ),
                    ]
                )
            ]
        )
        
        # This should NOT raise constraint violation
        result = await workout_repo.create_with_event(event, workout)
        
        assert result is not None
        assert result.workout.id is not None
        assert result.event.id is not None
        
        # Verify the workout was created
        created_workout = await workout_repo.get_by_id(result.workout.id)
        assert created_workout is not None
        assert len(created_workout.exercises) == 1
        
        exercise = created_workout.exercises[0]
        assert len(exercise.sets) == 2
        
        # Verify interval data was saved
        set1 = exercise.sets[0]
        assert set1.interval_description == "20s work, 10s rest"
        assert set1.work_duration_s == 20
        assert set1.rest_duration_s == 10
        assert set1.reps is None
        assert set1.weight_kg is None
    
    @pytest.mark.asyncio
    async def test_workout_with_mixed_interval_and_reps(self, db_connection, sample_data):
        """
        Verify workout can have both interval-based sets and rep-based sets.
        """
        db = db_connection
        workout_repo = WorkoutsRepository(db)
        
        # Create exercises
        rowing_ex = await sample_data.create_exercise("Rowing")
        squat_ex = await sample_data.create_exercise("Squats")
        
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title="Mixed Training Session",
            start_time=datetime.fromisoformat("2025-11-20T08:00:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        workout = WorkoutCreate(
            workout_name="Mixed Cardio and Strength",
            category=WorkoutCategory.MIXED,
            exercises=[
                # Exercise 1: Rowing (interval-based, no reps)
                WorkoutExercise(
                    exercise_id=rowing_ex,
                    sequence_order=1,
                    sets=[
                        ExerciseSet(
                            set_number=1,
                            set_type=SetType.WORKING,
                            interval_description="500m sprint",
                            duration_s=120,
                            distance_km=0.5
                        )
                    ]
                ),
                # Exercise 2: Squats (rep-based, no interval)
                WorkoutExercise(
                    exercise_id=squat_ex,
                    sequence_order=2,
                    sets=[
                        ExerciseSet(
                            set_number=1,
                            set_type=SetType.WORKING,
                            reps=10,
                            weight_kg=60.0
                        )
                    ]
                )
            ]
        )
        
        result = await workout_repo.create_with_event(event, workout)
        
        assert result is not None
        
        # Verify both exercises were created correctly
        created_workout = await workout_repo.get_by_id(result.workout.id)
        assert len(created_workout.exercises) == 2
        
        # Rowing (interval-based)
        rowing = created_workout.exercises[0]
        assert rowing.sets[0].interval_description == "500m sprint"
        assert rowing.sets[0].duration_s == 120
        assert rowing.sets[0].distance_km == 0.5
        assert rowing.sets[0].reps is None
        
        # Squats (rep-based)
        squats = created_workout.exercises[1]
        assert squats.sets[0].reps == 10
        assert squats.sets[0].weight_kg == 60.0
        assert squats.sets[0].interval_description is None
    
    @pytest.mark.asyncio
    async def test_constraint_still_enforced(self, db_connection, sample_data):
        """
        Verify database constraint still enforces that at least one of
        reps, distance_km, or interval_description must be provided.
        """
        db = db_connection
        workout_repo = WorkoutsRepository(db)
        
        ex = await sample_data.create_exercise("Test Exercise")
        
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title="Invalid Workout",
            start_time=datetime.fromisoformat("2025-11-20T09:00:00"),
            significance=Significance.ROUTINE,
            category="health",
            participants=[]
        )
        
        # Create workout with set that has NONE of: reps, distance_km, interval_description
        workout = WorkoutCreate(
            workout_name="Should Fail",
            category=WorkoutCategory.STRENGTH,
            exercises=[
                WorkoutExercise(
                    exercise_id=ex,
                    sequence_order=1,
                    sets=[
                        ExerciseSet(
                            set_number=1,
                            set_type=SetType.WORKING,
                            weight_kg=50.0,  # Has weight but no reps/interval/distance
                            reps=None,
                            interval_description=None,
                            distance_km=None
                        )
                    ]
                )
            ]
        )
        
        # This should fail the constraint check
        with pytest.raises(Exception) as exc_info:
            await workout_repo.create_with_event(event, workout)
        
        # Verify it's the constraint violation
        assert "check_reps_or_interval" in str(exc_info.value).lower() or \
               "constraint" in str(exc_info.value).lower()
