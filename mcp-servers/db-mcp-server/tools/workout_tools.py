"""
Workout Analytics MCP Tools
Specialized tools for workout tracking, progression, and training analysis.
"""

from mcp import types


def get_workout_tools() -> list[types.Tool]:
    """
    Returns only creation/write tools for workouts.

    Tools included:
    - create_workout: Create a workout with event
    - update_workout: Update workout metadata
    - reassign_exercise_in_workouts: Reassign exercise_id in workout_exercises for deduplication

    Delete/restore: use delete_entity / restore_entity with entity_type="workout".
    For searching exercises, use execute_sql_query instead (SQL-first architecture).
    """
    return [
        _create_workout_tool(),
        _update_workout_tool(),
        _reassign_exercise_in_workouts_tool(),
    ]


def get_exercise_tools() -> list[types.Tool]:
    """
    Returns only creation/write tools for exercises.

    Tools included:
    - create_exercise: Add custom exercises to catalog
    - update_exercise: Modify exercise details

    Delete/restore: use delete_entity / restore_entity with entity_type="exercise".
    For searching exercises, use execute_sql_query instead (SQL-first architecture).
    """
    return [
        _create_exercise_tool(),
        _update_exercise_tool(),
    ]


# Individual tool definitions
def _create_workout_tool() -> types.Tool:
    return types.Tool(
        name="create_workout",
        description="""Create a workout with event (event-first architecture).

✅ SUPPORTS TWO TYPES OF WORKOUTS:

1. GYM WORKOUTS (STRENGTH, CARDIO, FLEXIBILITY, MIXED)
   - Require exercises array with exercise_ids (use search_exercises tool first)
   - Each exercise must have sets with reps, weights, duration, etc.

2. SPORT WORKOUTS (SPORTS category with SPORT subtype or specific sports)
   - Exercises array is OPTIONAL (can be empty)
   - Use game_type, score, sport_type fields instead
   - Examples: Tennis, Pickleball, Basketball, Soccer, etc.

HYBRID RESOLUTION:
- location_id: Uses existing location (validates existence)
- participant_ids: Uses existing people (validates existence)
- exercises (optional): Required for GYM workouts only

EXTERNAL LINKING (e.g., Garmin, Apple Health, Fitbit):
- external_event_id: ID from external system (e.g., Garmin activity ID)
- external_event_source: Source system name ('garmin', 'apple_health', 'fitbit', 'strava')
- Use these to link workouts to external systems for detailed stats retrieval

EXAMPLE - GYM WORKOUT:
{
  "event": {
    "title": "Morning Strength Training",
    "start_time": "2025-10-12T09:00:00",
    "end_time": "2025-10-12T10:30:00",
        "location_id": "<location-uuid>",
    "participant_ids": ["<person-uuid>"]
  },
  "workout": {
    "workout_name": "Push Day",
    "category": "STRENGTH",
    "intensity": 8,
    "exercises": [
      {
        "exercise_id": "uuid-from-search",
        "sequence_order": 1,
        "sets": [
          {"set_number": 1, "set_type": "WARMUP", "weight_kg": 60, "reps": 10},
          {"set_number": 2, "set_type": "WORKING", "weight_kg": 80, "reps": 8}
        ]
      }
    ]
  }
}

EXAMPLE - SPORT WORKOUT:
{
  "event": {
    "title": "Tennis at Trisha's Pro Tennis Academy",
    "start_time": "2025-06-21T10:45:00",
    "end_time": "2025-06-21T12:30:00",
        "location_id": "<location-uuid>",
    "participant_ids": ["<person-uuid>"]
  },
  "workout": {
    "workout_name": "Tennis",
    "category": "SPORTS",
    "workout_subtype": "SPORT",
    "intensity": 7,
    "game_type": "singles",
    "score": "6-4 7-5"
  }
}

EXAMPLE - GARMIN-LINKED RUN:
{
  "event": {
    "title": "Morning 10K Run",
    "start_time": "2025-12-09T07:00:00",
    "end_time": "2025-12-09T07:55:00",
        "location_id": "<location-uuid>",
    "external_event_id": "20007876401",
    "external_event_source": "garmin"
  },
  "workout": {
    "workout_name": "10K Run",
    "category": "CARDIO",
    "workout_subtype": "RUN",
    "intensity": 7,
    "distance_km": 10.0
  }
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "event": {
                    "type": "object",
                    "description": "Event details (WHO, WHERE, WHEN)",
                    "properties": {
                        "title": {"type": "string", "description": "Event title"},
                        "description": {"type": "string", "description": "Event description (optional)"},
                        "start_time": {"type": "string", "description": "Start time (ISO 8601)"},
                        "end_time": {"type": "string", "description": "End time (ISO 8601, optional)"},
                        "category": {
                            "type": "string",
                            "enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
                            "description": "Event category. Default for workouts: health"
                        },
                        "significance": {
                            "type": "string",
                            "enum": ["routine", "notable", "major_milestone"],
                            "default": "routine"
                        },
                        "location_id": {"type": "string", "description": "Location UUID (if known)"},
                        "participant_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Participant UUIDs (if known)"
                        },
                        "parent_event_id": {
                            "type": "string",
                            "description": "UUID of parent event for hierarchical relationships (optional). Use this to create sub-events like 'workout during vacation' or 'activity during trip'."
                        },
                        "external_event_id": {
                            "type": "string",
                            "description": "ID from external system (e.g., Garmin activity ID '20007876401'). Use with external_event_source."
                        },
                        "external_event_source": {
                            "type": "string",
                            "description": "Source system for external_event_id (e.g., 'garmin', 'apple_health', 'fitbit', 'strava')"
                        },
                        "notes": {"type": "string", "description": "Additional notes"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "start_time"]
                },
                "workout": {
                    "type": "object",
                    "description": "Workout details (WHAT)",
                    "properties": {
                        "workout_name": {"type": "string", "description": "Workout name"},
                        "category": {
                            "type": "string",
                            "enum": ["STRENGTH", "CARDIO", "FLEXIBILITY", "SPORTS", "MIXED"],
                            "description": "Workout category"
                        },
                        "workout_subtype": {
                            "type": "string",
                            "enum": ["GYM_STRENGTH", "GYM_CARDIO", "RUN", "SWIM", "BIKE", "HIKE", "SPORT", "YOGA", "CROSSFIT", "CALISTHENICS", "DANCE", "MARTIAL_ARTS", "OTHER"],
                            "description": "Workout subtype (optional)"
                        },
                        "intensity": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Intensity level (1-10)"
                        },
                        "exercises": {
                            "type": "array",
                            "description": "List of exercises with sets (exercise_id REQUIRED from search_exercises)",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "exercise_id": {
                                        "type": "string",
                                        "description": "Exercise UUID (from search_exercises tool)"
                                    },
                                    "sequence_order": {
                                        "type": "integer",
                                        "description": "Order in workout (1, 2, 3...)"
                                    },
                                    "sets": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "set_number": {"type": "integer"},
                                                "set_type": {
                                                    "type": "string",
                                                    "enum": ["WARMUP", "WORKING", "DROP", "FAILURE"],
                                                    "default": "WORKING"
                                                },
                                                "weight_kg": {"type": "number"},
                                                "reps": {"type": "integer", "description": "Number of reps (required unless using interval_description)"},
                                                "duration_s": {"type": "integer", "description": "Total duration in seconds"},
                                                "distance_km": {"type": "number"},
                                                "pace": {"type": "string", "description": "Pace (e.g., '5:30/km')"},
                                                "rest_time_s": {"type": "integer", "description": "Rest time after set in seconds"},
                                                "work_duration_s": {"type": "integer", "description": "Work interval duration in seconds (for Tabata/HIIT)"},
                                                "rest_duration_s": {"type": "integer", "description": "Rest interval duration in seconds (for Tabata/HIIT)"},
                                                "interval_description": {"type": "string", "description": "Interval description (e.g., '8 rounds: 20s work / 10s rest'). Required if reps is null."},
                                                "notes": {"type": "string"}
                                            },
                                            "required": ["set_number"]
                                        }
                                    },
                                    "notes": {"type": "string"}
                                },
                                "required": ["exercise_id", "sequence_order", "sets"]
                            }
                        },
                        "distance_km": {"type": "number", "description": "Total distance (for cardio)"},
                        "sport_type": {"type": "string", "description": "Type of sport (e.g., 'Tennis', 'Pickleball', 'Basketball')"},
                        "game_type": {"type": "string", "description": "Type of game (e.g., 'singles', 'doubles', 'match')"},
                        "score": {"type": "string", "description": "Game score (e.g., '6-4 7-5' for tennis)"}
                    },
                    "required": ["workout_name", "category"]
                }
            },
            "required": ["event", "workout"]
        }
    )


def _update_workout_tool() -> types.Tool:
    return types.Tool(
        name="update_workout",
        description="""Update an existing workout. Can update workout metadata (name, category, subtype, sport_type), participants, and external system links.

NOTE: Workout stats like intensity, heart rate, distance, and pace are NOT stored in the DB.
For these metrics, link to Garmin/Strava via external_event_id and external_event_source.

EXAMPLE - Update category and subtype:
{
  "workout_id": "uuid-of-workout",
  "category": "CARDIO",
  "workout_subtype": "RUN"
}

EXAMPLE - Update participants:
{
  "workout_id": "uuid-of-workout",
  "participant_ids": ["<uuid-1>"]
}

EXAMPLE - Link to Garmin activity (retroactive linking):
{
  "workout_id": "uuid-of-workout",
  "external_event_id": "20007876401",
  "external_event_source": "garmin"
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "workout_id": {
                    "type": "string",
                    "description": "UUID of the workout to update (required)"
                },
                "workout_name": {
                    "type": "string",
                    "description": "Updated workout name (optional)"
                },
                "category": {
                    "type": "string",
                    "enum": ["STRENGTH", "CARDIO", "FLEXIBILITY", "SPORTS", "MIXED"],
                    "description": "Updated category (optional)"
                },
                "workout_subtype": {
                    "type": "string",
                    "enum": ["GYM_STRENGTH", "GYM_CARDIO", "RUN", "SWIM", "BIKE", "HIKE", "SPORT", "YOGA", "CROSSFIT", "CALISTHENICS", "DANCE", "MARTIAL_ARTS", "OTHER"],
                    "description": "Updated subtype (optional)"
                },
                "external_event_id": {
                    "type": "string",
                    "description": "Link to external system ID (e.g., Garmin activity ID). Use with external_event_source for retroactive linking."
                },
                "external_event_source": {
                    "type": "string",
                    "description": "Source system for external_event_id (e.g., 'garmin', 'apple_health', 'fitbit', 'strava')"
                },
                "participant_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Updated list of participant UUIDs for the workout event (replaces existing participants, optional)"
                }
            },
            "required": ["workout_id"]
        }
    )


def _create_exercise_tool() -> types.Tool:
    return types.Tool(
        name="create_exercise",
        description="Create a new custom exercise. Use this to add exercises not in the catalog. Users need this for custom movements, variations, or sport-specific exercises.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exercise name (e.g., 'Bulgarian Split Squat', 'Landmine Press')"
                },
                "category": {
                    "type": "string",
                    "description": "Exercise category",
                    "enum": ["strength", "cardio", "flexibility", "sports", "plyometric"]
                },
                "primary_muscle_group": {
                    "type": "string",
                    "description": "Primary muscle group targeted (e.g., 'chest', 'legs', 'back', 'shoulders', 'arms', 'core')"
                },
                "secondary_muscle_groups": {
                    "type": "array",
                    "description": "Secondary muscle groups (optional)",
                    "items": {"type": "string"}
                },
                "equipment": {
                    "type": "array",
                    "description": "Equipment required (e.g., ['barbell'], ['dumbbells', 'bench']) (optional)",
                    "items": {"type": "string"}
                },
                "variants": {
                    "type": "array",
                    "description": "Exercise variants (e.g., ['wide grip', 'close grip']) (optional)",
                    "items": {"type": "string"}
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes about the exercise (optional)"
                }
            },
            "required": ["name", "category", "primary_muscle_group"]
        }
    )


def _update_exercise_tool() -> types.Tool:
    return types.Tool(
        name="update_exercise",
        description="Update an existing exercise. Use this to fix typos, update muscle groups, change categories, or modify equipment lists.",
        inputSchema={
            "type": "object",
            "properties": {
                "exercise_id": {
                    "type": "string",
                    "description": "UUID of the exercise to update (required)"
                },
                "name": {
                    "type": "string",
                    "description": "Update exercise name (optional)"
                },
                "category": {
                    "type": "string",
                    "description": "Update category (optional)",
                    "enum": ["strength", "cardio", "flexibility", "sports", "plyometric"]
                },
                "primary_muscle_group": {
                    "type": "string",
                    "description": "Update primary muscle group (optional)"
                },
                "secondary_muscle_groups": {
                    "type": "array",
                    "description": "Update secondary muscle groups (optional - replaces existing)",
                    "items": {"type": "string"}
                },
                "equipment": {
                    "type": "array",
                    "description": "Update equipment list (optional - replaces existing)",
                    "items": {"type": "string"}
                },
                "variants": {
                    "type": "array",
                    "description": "Update variants list (optional - replaces existing)",
                    "items": {"type": "string"}
                },
                "notes": {
                    "type": "string",
                    "description": "Update notes (optional)"
                }
            },
            "required": ["exercise_id"]
        }
    )


def _reassign_exercise_in_workouts_tool() -> types.Tool:
    return types.Tool(
        name="reassign_exercise_in_workouts",
        description="""Reassign exercise_id in workout_exercises table for exercise deduplication/merging.

Use this tool when merging duplicate exercises: update all workout_exercises records
to point from the duplicate exercise to the canonical exercise.

USE CASES:
- Merging duplicate exercises (e.g., 'Pull Up' -> 'Pull-up')
- Consolidating variants (e.g., 'Kettlebell Row' -> 'Row')
- Fixing typos in exercise names after creating workouts

EXAMPLE - Merge duplicate exercise:
{
  "old_exercise_id": "uuid-of-duplicate-exercise",
  "new_exercise_id": "uuid-of-canonical-exercise"
}

After running this tool, you can safely delete the duplicate exercise.

NOTE: This updates ALL workout_exercises records that reference old_exercise_id.
Use execute_sql_query first to preview affected records:
  SELECT we.id, w.workout_name, e.name as exercise_name, ev.start_time
  FROM workout_exercises we
  JOIN workouts w ON we.workout_id = w.id
  JOIN exercises e ON we.exercise_id = e.id
  JOIN events ev ON w.event_id = ev.id
  WHERE we.exercise_id = '<old_exercise_id>'""",
        inputSchema={
            "type": "object",
            "properties": {
                "old_exercise_id": {
                    "type": "string",
                    "description": "UUID of the exercise being deprecated/merged (the duplicate)"
                },
                "new_exercise_id": {
                    "type": "string",
                    "description": "UUID of the canonical exercise to use instead"
                }
            },
            "required": ["old_exercise_id", "new_exercise_id"]
        }
    )
