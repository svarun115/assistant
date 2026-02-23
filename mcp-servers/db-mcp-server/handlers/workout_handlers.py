"""
Workout Handlers
Handles: get_recent_workouts, get_exercise_progression, get_muscle_group_balance, 
         get_cardio_workouts, get_sport_workouts, create_workout
"""

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from mcp import types

from models import (
    EventCreate, EventType, EventParticipant, Significance,
    WorkoutCreate, WorkoutCategory, WorkoutExercise, ExerciseSet, SetType,
)


def serialize_result(obj):
    """Helper to serialize datetime and other non-JSON types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def resolve_location(
    repos,
    location_id: Optional[str] = None
) -> Optional[UUID]:
    """
    Resolve location_id to UUID (no auto-create by name).
    """
    if location_id:
        try:
            location_uuid = UUID(location_id)
            location = await repos.locations.get_by_id(location_uuid)
            if not location:
                raise ValueError(f"Location with ID {location_id} not found")
            return location.id
        except ValueError as e:
            raise ValueError(f"Invalid location_id format: {e}")
    return None


async def resolve_participants(
    repos,
    participant_ids: list[str] = None,
    role: str = "participant"
) -> list[EventParticipant]:
    """
    Resolve participant_ids to EventParticipant objects.
    
    Only accepts participant_ids (UUIDs). People must be created separately.
    """
    participants = []
    
    if participant_ids:
        for person_id_str in participant_ids:
            try:
                person_uuid = UUID(person_id_str)
                person = await repos.people.get_by_id(person_uuid)
                if not person:
                    raise ValueError(f"Person with ID {person_id_str} not found")
                participants.append(EventParticipant(person_id=person.id, role=role))
            except ValueError as e:
                raise ValueError(f"Invalid participant_id format: {e}")
    
    return participants


async def validate_exercises(repos, exercise_ids: list[str]) -> list[UUID]:
    """
    Validate that all exercise IDs exist (cannot auto-create exercises).
    Raises helpful error if not found.
    """
    validated_ids = []
    
    for exercise_id_str in exercise_ids:
        try:
            exercise_uuid = UUID(exercise_id_str)
            exercise = await repos.exercises.get_by_id(exercise_uuid)
            
            if not exercise:
                raise ValueError(
                    f"❌ Exercise with ID {exercise_id_str} not found.\n\n"
                    f"Exercises must exist before creating workouts (they contain metadata like "
                    f"muscle groups, equipment, etc.).\n\n"
                    f"🔍 Use search_exercises tool first:\n"
                    f"   search_exercises(search_term='bench press')\n\n"
                    f"If the exercise doesn't exist, you'll need to create it first using "
                    f"propose_write_query with an INSERT statement."
                )
            
            validated_ids.append(exercise.id)
        except ValueError as e:
            raise ValueError(f"Invalid exercise_id format: {e}")
    
    return validated_ids


async def handle_create_workout(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Create a workout with event (event-first pattern) with hybrid resolution"""
    try:
        event_data = arguments["event"]
        workout_data = arguments["workout"]
        
        # Reject participant_names parameter (use participant_ids only)
        if "participant_names" in event_data:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'participant_names' is no longer supported. Use 'participant_ids' with UUIDs instead. Create people first using create_person tool if needed."
                }, indent=2)
            )]

        # Reject location_name parameter (use location_id only)
        if "location_name" in event_data:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'location_name' is no longer supported. Use 'location_id' (UUID) instead. If you only have a name, call search_locations/create_location first, then pass the resulting location_id."
                }, indent=2)
            )]
        
        # Resolve location
        location_id = await resolve_location(
            repos,
            location_id=event_data.get("location_id")
        )
        
        # Resolve participants
        participants = await resolve_participants(
            repos,
            participant_ids=event_data.get("participant_ids")
        )
        
        # Parse timestamps
        start_time = datetime.fromisoformat(event_data["start_time"])
        end_time = None
        if event_data.get("end_time"):
            end_time = datetime.fromisoformat(event_data["end_time"])
        
        # Validate parent_event_id if provided
        parent_event_id = None
        if event_data.get("parent_event_id"):
            try:
                parent_event_id = UUID(event_data["parent_event_id"])
                # Verify parent event exists
                async with db.pool.acquire() as conn:
                    parent_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM events WHERE id = $1 AND is_deleted = false)",
                        parent_event_id
                    )
                    if not parent_exists:
                        raise ValueError(f"Parent event with ID {event_data['parent_event_id']} not found or is deleted")
            except ValueError as e:
                raise ValueError(f"Invalid parent_event_id: {e}")
        
        # Create event with external system references
        event = EventCreate(
            event_type=EventType.WORKOUT,
            title=event_data["title"],
            description=event_data.get("description"),
            start_time=start_time,
            end_time=end_time,
            location_id=location_id,
            parent_event_id=parent_event_id,
            category=event_data.get("category", "health"),
            significance=Significance(event_data.get("significance", "routine")),
            participants=participants,
            notes=event_data.get("notes"),
            tags=event_data.get("tags", []),
            external_event_id=event_data.get("external_event_id"),
            external_event_source=event_data.get("external_event_source")
        )
        
        # Validate and process exercises
        exercises = []
        for ex_data in workout_data.get("exercises", []):
            # Validate exercise exists
            exercise_ids = await validate_exercises(repos, [ex_data["exercise_id"]])
            
            # Process sets
            sets = []
            for set_data in ex_data.get("sets", []):
                exercise_set = ExerciseSet(
                    set_number=set_data["set_number"],
                    set_type=SetType(set_data.get("set_type", "WORKING")),
                    weight_kg=set_data.get("weight_kg"),
                    reps=set_data.get("reps"),
                    duration_s=set_data.get("duration_s"),
                    distance_km=set_data.get("distance_km"),
                    pace=set_data.get("pace"),
                    rest_time_s=set_data.get("rest_time_s"),
                    work_duration_s=set_data.get("work_duration_s"),
                    rest_duration_s=set_data.get("rest_duration_s"),
                    interval_description=set_data.get("interval_description"),
                    notes=set_data.get("notes")
                )
                sets.append(exercise_set)
            
            workout_exercise = WorkoutExercise(
                exercise_id=exercise_ids[0],
                sequence_order=ex_data["sequence_order"],
                sets=sets,
                notes=ex_data.get("notes")
            )
            exercises.append(workout_exercise)
        
        # Create workout
        workout = WorkoutCreate(
            workout_name=workout_data["workout_name"],
            category=WorkoutCategory(workout_data["category"]),
            workout_subtype=workout_data.get("workout_subtype"),
            intensity=workout_data.get("intensity"),
            exercises=exercises,
            distance_km=workout_data.get("distance_km"),
            sport_type=workout_data.get("sport_type"),
            game_type=workout_data.get("game_type"),
            score=workout_data.get("score")
        )
        
        # Create workout with event
        created = await repos.workouts.create_with_event(event, workout)
        
        result = {
            "event_id": str(created.event.id),
            "workout_id": str(created.workout.id),
            "title": created.event.title,
            "start_time": created.event.start_time.isoformat(),
            "location": created.event.location_name,
            "participants": [p.person_name for p in created.event.participants],
            "workout_name": created.workout.workout_name,
            "category": created.workout.category,
            "total_exercises": created.workout.total_exercises,
            "total_sets": created.workout.total_sets,
            "total_volume_kg": created.workout.total_volume_kg,
            "message": "✅ Workout created successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
        
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating workout: {str(e)}"}, indent=2)
        )]


async def handle_update_workout(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update an existing workout metadata, participants, and external system links"""
    try:
        workout_id = UUID(arguments["workout_id"])
        
        # Verify workout exists
        workout = await repos.workouts.get_by_id(workout_id)
        if not workout:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Workout {workout_id} not found"}, indent=2)
            )]
        
        # Build update dictionary for workout table
        workout_updates = {}
        
        if "workout_name" in arguments:
            workout_updates["workout_name"] = arguments["workout_name"]
        
        if "category" in arguments:
            workout_updates["category"] = arguments["category"]
        
        if "workout_subtype" in arguments:
            subtype = arguments["workout_subtype"]
            workout_updates["workout_subtype"] = subtype.lower() if isinstance(subtype, str) else subtype

        if "sport_type" in arguments:
            workout_updates["sport_type"] = arguments["sport_type"]
        
        # Build update dictionary for event table (external system links)
        event_updates = {}
        
        if "external_event_id" in arguments:
            event_updates["external_event_id"] = arguments["external_event_id"]
        
        if "external_event_source" in arguments:
            event_updates["external_event_source"] = arguments["external_event_source"]
        
        has_workout_updates = bool(workout_updates)
        has_event_updates = bool(event_updates)
        has_participant_updates = "participant_ids" in arguments
        
        if not has_workout_updates and not has_event_updates and not has_participant_updates:
            return [types.TextContent(
                type="text",
                text="⚠️ No fields to update"
            )]
        
        # Update workout table
        if has_workout_updates:
            # WorkoutsRepository.update_workout updates by event_id
            await repos.workouts.update_workout(workout.event_id, workout_updates)
        
        # Handle participants update if provided
        if has_participant_updates:
            participants = await resolve_participants(
                repos,
                participant_ids=arguments.get("participant_ids")
            )
            event_updates["participants"] = participants
        
        # Update event table (external links and/or participants)
        if event_updates:
            await repos.events.update(workout.event_id, event_updates)
        
        result = {
            "workout_id": str(workout_id),
            "event_id": str(workout.event_id),
            "message": "✅ Workout updated successfully"
        }
        
        # Include external link info if set
        if "external_event_id" in arguments or "external_event_source" in arguments:
            result["external_event_id"] = arguments.get("external_event_id")
            result["external_event_source"] = arguments.get("external_event_source")
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
        
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating workout: {str(e)}"}, indent=2)
        )]


async def handle_delete_workout(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete a workout by marking its event as deleted"""
    try:
        event_id = arguments["event_id"]
        
        query = """
            UPDATE events 
            SET is_deleted = true, deleted_at = NOW()
            WHERE id = $1
            RETURNING id, title, start_time
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, event_id)
            
            if not row:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Workout event with ID {event_id} not found"}, indent=2)
                )]
            
            result = {
                "event_id": str(row['id']),
                "title": row['title'],
                "start_time": row['start_time'].isoformat(),
                "message": "✅ Workout deleted successfully (soft delete)"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, default=serialize_result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting workout: {str(e)}"}, indent=2)
        )]


async def handle_undelete_workout(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Restore a previously deleted workout"""
    try:
        event_id = arguments["event_id"]
        
        query = """
            UPDATE events 
            SET is_deleted = false, deleted_at = NULL
            WHERE id = $1
            RETURNING id, title, start_time
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, event_id)
            
            if not row:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Workout event with ID {event_id} not found"}, indent=2)
                )]
            
            result = {
                "event_id": str(row['id']),
                "title": row['title'],
                "start_time": row['start_time'].isoformat(),
                "message": "✅ Workout restored successfully"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, default=serialize_result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring workout: {str(e)}"}, indent=2)
        )]


async def handle_reassign_exercise_in_workouts(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """
    Reassign exercise_id in workout_exercises table for exercise deduplication/merging.
    
    Updates all workout_exercises records from old_exercise_id to new_exercise_id.
    """
    try:
        old_exercise_id = UUID(arguments["old_exercise_id"])
        new_exercise_id = UUID(arguments["new_exercise_id"])
        
        # Validate old exercise exists
        old_exercise = await repos.exercises.get_by_id(old_exercise_id)
        if not old_exercise:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Old exercise with ID {old_exercise_id} not found"
                }, indent=2)
            )]
        
        # Validate new exercise exists
        new_exercise = await repos.exercises.get_by_id(new_exercise_id)
        if not new_exercise:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"New exercise with ID {new_exercise_id} not found"
                }, indent=2)
            )]
        
        # Prevent self-reassignment
        if old_exercise_id == new_exercise_id:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "old_exercise_id and new_exercise_id cannot be the same"
                }, indent=2)
            )]
        
        # Update all workout_exercises records
        query = """
            UPDATE workout_exercises 
            SET exercise_id = $2
            WHERE exercise_id = $1
            RETURNING id, workout_id
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, old_exercise_id, new_exercise_id)
            
            affected_count = len(rows)
            affected_workout_ids = list(set(str(row['workout_id']) for row in rows))
            
            result = {
                "old_exercise_id": str(old_exercise_id),
                "old_exercise_name": old_exercise.canonical_name,
                "new_exercise_id": str(new_exercise_id),
                "new_exercise_name": new_exercise.canonical_name,
                "affected_workout_exercise_count": affected_count,
                "affected_workout_count": len(affected_workout_ids),
                "affected_workout_ids": affected_workout_ids,
                "message": f"✅ Reassigned {affected_count} workout_exercises record(s) from '{old_exercise.canonical_name}' to '{new_exercise.canonical_name}'"
            }
            
            if affected_count == 0:
                result["message"] = f"⚠️ No workout_exercises records found referencing exercise '{old_exercise.canonical_name}'"
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, default=serialize_result, indent=2)
            )]
    
    except ValueError as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Invalid UUID format: {str(e)}"}, indent=2)
        )]
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error reassigning exercise: {str(e)}"}, indent=2)
        )]
