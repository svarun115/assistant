# Workouts - Complete Reference

**Comprehensive workout tracking with exercises, sets, progression analysis, and cardio/sport activities.**

---

## Quick Reference

**Key Tools:**
- `search_exercises` - **REQUIRED FIRST** - Find existing exercises before creating workouts
- `create_workout` - Create new workouts with exercises and training data
- SQL via `execute_sql_query` - Query recent workouts, progression, muscle balance, cardio, sports

---

## Available Tools

### 0. `search_exercises` **[REQUIRED FIRST STEP]**
**Search for existing exercises before creating workouts**

**ALWAYS use before creating workouts** - Exercises MUST exist in the system

**Parameters:**
```json
{
  "search_term": "string (required)",     // e.g., "bench press", "squat"
  "category": "string (optional)",        // Filter: 'strength', 'cardio', 'flexibility', 'sports', 'plyometric'
  "muscle_group": "string (optional)",    // Filter: e.g., 'chest', 'legs', 'back', 'shoulders'
  "limit": "integer (optional, default: 10)"
}
```

**Returns:** Exercise ID, name, category, muscle groups, equipment, description

**Example:** `search_exercises("bench press")`

**Important:** Use the returned `exercise_id` when creating workouts. Exercises cannot be auto-created like people/locations.

---

### 0. `search_exercises` **[REQUIRED FIRST STEP]**
**Search for existing exercises before creating workouts**

**ALWAYS use before creating workouts** - Exercises MUST exist in the system

**Parameters:**
```json
{
  "search_term": "string (required)",     // e.g., "bench press", "squat"
  "category": "string (optional)",        // Filter: 'strength', 'cardio', 'flexibility', 'sports', 'plyometric'
  "muscle_group": "string (optional)",    // Filter: e.g., 'chest', 'legs', 'back', 'shoulders'
  "limit": "integer (optional, default: 10)"
}
```

**Returns:** Exercise ID, name, category, muscle groups, equipment, description

**Example:** `search_exercises("bench press")`

**Important:** Use the returned `exercise_id` when creating workouts. Exercises cannot be auto-created like people/locations.

---

## SQL Query Patterns for Workouts

**All workout queries use `execute_sql_query()`**

### Get Recent Workouts
```sql
SELECT 
    w.id, w.workout_name, e.start_time::date as workout_date,
    w.category, w.intensity, w.distance_km,
    l.canonical_name as location,
    STRING_AGG(DISTINCT ex.name, ', ') as exercises
FROM workouts w
JOIN events e ON w.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN workout_exercises we ON w.id = we.workout_id
LEFT JOIN exercises ex ON we.exercise_id = ex.id
WHERE e.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY w.id, e.id, l.canonical_name
ORDER BY e.start_time DESC
LIMIT 10;
```

### Track Exercise Progression
```sql
SELECT 
    e.name as exercise,
    w.set_number,
    s.reps,
    s.weight_kg,
    s.volume_kg,
    ev.start_time::date as workout_date
FROM exercises e
JOIN workout_exercises we ON e.id = we.exercise_id
JOIN workout_sets s ON we.id = s.workout_exercise_id
JOIN workouts w ON we.workout_id = w.id
JOIN events ev ON w.event_id = ev.id
WHERE LOWER(e.name) LIKE '%bench press%'
  AND ev.start_time >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY ev.start_time ASC;
```

### Analyze Muscle Group Balance
```sql
SELECT 
    e.muscle_group,
    COUNT(DISTINCT w.id) as workout_count,
    COUNT(DISTINCT s.id) as total_sets,
    ROUND(SUM(s.volume_kg)::numeric, 2) as total_volume,
    ROUND((COUNT(DISTINCT s.id)::numeric / 
           (SELECT COUNT(*) FROM workout_sets s2 
            JOIN workout_exercises we2 ON s2.workout_exercise_id = we2.id
            JOIN workouts w2 ON we2.workout_id = w2.id
            JOIN events ev2 ON w2.event_id = ev2.id
            WHERE ev2.start_time >= CURRENT_DATE - INTERVAL '30 days') * 100), 2) as pct_of_volume
FROM exercises e
JOIN workout_exercises we ON e.id = we.exercise_id
JOIN workout_sets s ON we.id = s.workout_exercise_id
JOIN workouts w ON we.workout_id = w.id
JOIN events ev ON w.event_id = ev.id
WHERE ev.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY e.muscle_group
ORDER BY total_volume DESC;
```

### Get Cardio Workouts
```sql
SELECT 
    w.id, w.workout_name, e.start_time::date as workout_date,
    EXTRACT(EPOCH FROM (e.end_time - e.start_time))/60 as duration_minutes,
    w.distance_km,
    CASE WHEN w.distance_km > 0 
         THEN ROUND((EXTRACT(EPOCH FROM (e.end_time - e.start_time))/60 / w.distance_km)::numeric, 2)
         ELSE NULL 
    END as pace_min_per_km,
    w.intensity,
    l.canonical_name as location
FROM workouts w
JOIN events e ON w.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
WHERE w.workout_subtype IN ('RUN', 'SWIM', 'BIKE', 'HIKE')
  AND e.start_time >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY e.start_time DESC;
```

### Get Sport Workouts
```sql
SELECT 
    w.id, w.workout_name, e.start_time::date as workout_date,
    w.sport_type, w.game_type, w.score,
    w.intensity,
    l.canonical_name as location,
    STRING_AGG(DISTINCT p.canonical_name, ', ') as participants
FROM workouts w
JOIN events e ON w.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN event_participants ep ON e.id = ep.event_id
LEFT JOIN people p ON ep.person_id = p.id
WHERE w.workout_subtype = 'SPORT'
  AND e.start_time >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY w.id, e.id, l.canonical_name
ORDER BY e.start_time DESC;
```

---

## Write Tool: `create_workout`

---

### 6. `create_workout` ✍️
**Create workouts with exercises and training data**

**When to use:**
- Creating workouts from journal entries
- Recording training sessions with exercises and sets
- Tracking cardio activities (runs, swims, bike rides)
- Logging sports activities

**Parameters:**
```json
{
  "event": {
    "title": "Morning Strength Training",                  // Required
    "description": "Push day workout",                     // Optional
    "start_time": "2025-10-12T09:00:00",                  // Required (ISO 8601)
    "end_time": "2025-10-12T10:30:00",                    // Optional
    "category": "fitness",                                 // Optional
    "significance": "routine",                             // Optional: "routine", "notable", "major_milestone"

    // Location (optional): provide a location_id (write tools accept only location_id)
    "location_id": "uuid-from-search-or-create_location",
    
    "participant_names": ["Mike"],                         // Auto-creates if needed
    // OR
    "participant_ids": ["uuid-1"],                        // Validates exist
    
    "notes": "Felt strong today!",                        // Optional
    "tags": ["strength", "compound"]                       // Optional
  },
  "workout": {
    "workout_name": "Push Day",                           // Optional
    "category": "strength",                                // Required: "strength", "cardio", "flexibility", "sports", "mixed"
    "workout_subtype": "GYM_STRENGTH",                    // Optional: "RUN", "SWIM", "BIKE", "HIKE", etc.
    "intensity": 8,                                        // Optional: 1-10 scale
    
    "exercises": [                                         // Optional (required for strength workouts)
      {
        "exercise_id": "uuid-bench-press",                // ⚠️ MUST exist (use search_exercises first)
        "sequence_order": 1,
        "sets": [
          {
            "set_number": 1,
            "set_type": "warmup",                         // "warmup", "working", "dropset", "failure", "amrap"
            "weight_kg": 60,
            "reps": 10,
            "rest_time_s": 120                            // Optional
          },
          {
            "set_number": 2,
            "set_type": "working",
            "weight_kg": 80,
            "reps": 8,
            "rest_time_s": 120
          }
        ],
        "notes": "Good form"                              // Optional
      }
    ],
    
    // Cardio-specific fields (optional)
    "distance_km": 5.2,                                   // For runs, bike rides, swims
    "pace": "5:30/km",                                    // Pace string
    "avg_heart_rate": 145,                                // Average HR
    "max_heart_rate": 170                                 // Max HR
  }
}
```

**Dependency Chain:**
1. **Location**: Validated via `location_id`
2. **People**: Auto-created via `participant_names` OR validated via `participant_ids`
3. **Exercises**: **MUST exist** - use `search_exercises` first to get UUIDs
4. **Event**: Created with resolved references
5. **Workout**: Created with event_id and exercises

**Critical: Exercises Cannot Be Auto-Created**

Exercises require metadata (muscle groups, equipment, categories) that cannot be inferred from just a name. Always use `search_exercises` first:

```javascript
// Step 1: Search for exercises
search_exercises(search_term: "bench press")
// Returns: {id: "uuid-bench-press", canonical_name: "Bench Press", ...}

// Step 2: Create workout with exercise UUIDs
create_workout(
  event: {...},
  workout: {
    exercises: [{exercise_id: "uuid-bench-press", ...}]
  }
)
```

**Usage Patterns:**

**Pattern 1: Strength Workout**
```json
{
  "event": {
    "title": "Leg Day",
    "start_time": "2025-10-12T18:00:00",
    "location_id": "uuid-from-search-or-create_location",
    "participant_names": ["Training Partner"]
  },
  "workout": {
    "category": "strength",
    "workout_subtype": "GYM_STRENGTH",
    "intensity": 9,
    "exercises": [
      {
        "exercise_id": "squat-uuid",  // From search_exercises
        "sequence_order": 1,
        "sets": [
          {"set_number": 1, "set_type": "warmup", "weight_kg": 60, "reps": 10},
          {"set_number": 2, "set_type": "working", "weight_kg": 100, "reps": 5}
        ]
      }
    ]
  }
}
```

**Pattern 2: Cardio Workout**
```json
{
  "event": {
    "title": "Morning Run",
    "start_time": "2025-10-12T06:00:00",
    "end_time": "2025-10-12T06:35:00",
    "location_id": "uuid-from-search-or-create_location"
  },
  "workout": {
    "category": "cardio",
    "workout_subtype": "RUN",
    "intensity": 7,
    "distance_km": 5.2,
    "pace": "5:30/km",
    "avg_heart_rate": 145,
    "max_heart_rate": 170
  }
}
```

**Best Practices:**
- **Always search for exercises first** using `search_exercises` before creating workouts
- Use `participant_names` for quick entry (auto-creates people if needed)
- Use `participant_ids`/`location_id` when you have UUIDs from searches
- Provide timestamps in ISO 8601 format
- Don't guess exercise UUIDs - they must exist in the database
- For cardio and sports, you can omit exercises array

**Error Handling:**
- Missing exercise ID → Error message suggesting to use `search_exercises`
- Invalid UUID format → Error with correct format
---

## Tool Usage

**Typical workflows:**
- General overview → Use SQL: "Get Recent Workouts" (section above)
- Specific exercise progress → Use SQL: "Track Exercise Progression" (section above)
- Cardio tracking → Use SQL: "Get Cardio Workouts" (section above)
- Sports tracking → Use SQL: "Get Sport Workouts" (section above)
- Training balance → Use SQL: "Analyze Muscle Group Balance" (section above)

**SQL-First Philosophy:** Use `execute_sql_query()` with the patterns above for all data retrieval.

---

## Journal Extraction Guide

### Extraction Example

**Gym Workout:**
```
Journal: "Morning gym session. Bench press: 3 sets of 8 at 185 lbs. Squats: 4x10 at 225."

create_workout({
  event: {
    title: "Morning gym session",
    start_time: "2025-10-12T09:00:00",
    location_id: "uuid-from-search-or-create_location"
  },
  workout: {
    category: "STRENGTH",
    workout_subtype: "GYM_STRENGTH",
    exercises: [
      {exercise_id: "bench-press-uuid", sequence_order: 1, sets: [{set_number: 1, weight_kg: 83.91, reps: 8}, ...]},
      {exercise_id: "squat-uuid", sequence_order: 2, sets: [{set_number: 1, weight_kg: 102.06, reps: 10}, ...]}
    ]
  }
})
```

### Extraction Guidelines

**Unit Conversions:**
- Weight: Store in kg (1 lb = 0.453592 kg)
- Distance: Store in km (1 mile = 1.60934 km)
- Time: Store in seconds

**Set Types:**
- Lighter first sets → WARMUP
- "To failure" / AMRAP → FAILURE
- "Drop set" → DROP
- Otherwise → WORKING

**Workout Times (if unspecified):**
- "Morning" → 06:00:00
- "Lunch" → 12:00:00
- "Evening" → 18:00:00

---

## Important Notes

1. **Search exercises first**: Use `search_exercises()` before creating workouts
2. **Event-centric design**: Workouts reference events for WHO, WHERE, WHEN
3. **Convenience views**: Use `workout_events` view for simpler queries
4. **Minimal philosophy**: Store structure (exercises, sets), not metrics (heart rate, GPS)
5. **Notes over fields**: Use notes for qualitative data, fields for quantitative

---

## 📚 Related Resources

- **`EVENTS.md`** - Event-centric architecture and event types
- **`PEOPLE.md`** - Training partners and participants
- **`LOCATIONS.md`** - Gym and workout location reference
