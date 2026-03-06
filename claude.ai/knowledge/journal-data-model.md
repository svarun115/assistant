# Journal Data Model

Critical patterns and gotchas for the personal-journal MCP. Tool schemas are self-documenting — this covers only what schemas don't tell you.

---

## Event-First Querying (Most Important Rule)

Workouts, meals, commutes, and entertainment are **event specializations**. They do NOT have their own date/time/location/participant fields — those live on the parent `events` entity.

**Rule:** To filter by date, time, location, or participants → query `events` with a `type` filter. Use `include` to hydrate specialization data. Only query the child entity directly when filtering by specialization-specific fields.

**Valid filterable fields per entity:**

| Entity | Filterable Fields |
|--------|-------------------|
| `events` | `id`, `type`, `title`, `description`, `date`, `start`, `end`, `duration`, `location_id`, `category`, `significance`, `notes`, `tags` |
| `workouts` | `id`, `event_id`, `name`, `category`, `subtype`, `sport_type` |
| `meals` | `id`, `event_id`, `meal_title`, `meal_type`, `cuisine`, `portion_size` |
| `commutes` | `id`, `event_id`, `transport_mode`, `from_location_id`, `to_location_id` |
| `entertainment` | `id`, `event_id`, `entertainment_type`, `title`, `personal_rating`, `completion_status` |

**Common mistakes:**
- Querying `workouts` with `date >= X` — WRONG (date is on events, not workouts)
- Querying `events` with `start_time >= X` — WRONG (field is `start`, not `start_time`)
- Querying `commutes` with `date >= X` — WRONG (use `events` with `type: "commute"`)

---

## Critical Tool Gotchas

### participant_ids REPLACES, Not Appends

`update_event(event_id, participant_ids=[...])` replaces ALL participants.

**Steps:**
1. Query current event with `include: ["participants"]`
2. Build complete list including existing + changes
3. Pass the full list

Wrong: just passing the new person to add (removes everyone else!)

### place_id for Public Venues (Mandatory)

Always call `search_places()` first for public venues (restaurants, gyms, parks). Use returned `place_id` when creating the location.

### Garmin Metrics Stay in Garmin

Do NOT copy Garmin stats (distance, pace, HR) into event notes or DB fields. Link via `external_event_id` + `external_event_source: "garmin"` and query Garmin when stats are needed.

### create_entertainment Requires event_type

`create_entertainment` does NOT auto-set `event_type` (unlike `create_workout`/`create_meal`/`create_commute`). Always include `"event_type": "generic"` in the event object.

---

## Merge Workflows

### Merging Duplicate People

1. Identify canonical (more events/relationships)
2. Query events with `participants.name` filter for duplicate
3. For EACH event: `update_event(event_id, participant_ids=[...])` with canonical ID
4. Verify no events reference duplicate
5. `delete_person(person_id)` on duplicate

### Merging Duplicate Exercises

1. `reassign_exercise_in_workouts(old_exercise_id, new_exercise_id)` — updates ALL workout references
2. `delete_exercise(exercise_id)` on duplicate

---

## Health Condition Logging

Before calling `log_health_condition_update`, always check for existing log on that `(condition_id, log_date)`:
```
query(entity: "health_condition_logs", where: {condition_id: "<id>", log_date: "<date>"})
```
If exists, use `update_health_condition_log` instead — otherwise unique constraint violation.

---

## Query Discipline

Before any query with `include`, estimate payload: rows × nested objects × ~200 chars.

**High-risk:** Workouts with `include: ["exercises"]` across wide date ranges (5-10 exercises × sets per workout). Always scope by date or use `limit < 15`. Need exercise data across many workouts? Query the `exercises` catalog separately, join in-context by `exercise_id`.

**If overflow:** STOP — do not parse. Re-query with tighter filters (narrower date range, fewer includes, lower limit). Split into multiple smaller queries.

**Two-strike bail-out:** Same tool/entity fails twice with similar errors → STOP and pivot.

| Error Type | How to Recognize | Action |
|-----------|-----------------|--------|
| Server-side | `column X does not exist` | Report to user — entity config mismatch |
| Overflow | Result too large | Re-query with tighter scope |
| Field validation | Returns `validFields` list | Use suggested valid fields (self-correctable, one retry ok) |

Field validation errors are self-correctable. Server-side errors are NOT — retrying with different field names is futile.

**Exercises include:** `include: ["exercises"]` on workouts returns fully hydrated rows — nested exercise entity (name, muscle_group, equipment) + nested sets. No separate query needed for muscle group analysis.

---

## Enum Quick Reference

| Tool / Field | Valid Values |
|-------------|-------------|
| `transport_mode` (commute) | `driving`, `public_transit`, `walking`, `cycling`, `running`, `flying`, `rideshare`, `taxi`, `train`, `bus`, `subway`, `ferry`, `scooter`, `other` |
| `portion_size` (meal) | `small`, `medium`, `large`, `extra_large` |
| `meal_title` (meal) | `breakfast`, `lunch`, `dinner`, `snack`, `brunch`, `dessert` |
| `meal_type` (meal) | `home_cooked`, `restaurant`, `takeout`, `meal_prep`, `fast_food`, `buffet` |
| `workout category` | `STRENGTH`, `CARDIO`, `FLEXIBILITY`, `SPORTS`, `MIXED` |
| `workout_subtype` | `GYM_STRENGTH`, `GYM_CARDIO`, `RUN`, `SWIM`, `BIKE`, `HIKE`, `SPORT`, `YOGA`, `CROSSFIT`, `CALISTHENICS`, `DANCE`, `MARTIAL_ARTS`, `OTHER` |
| `set_type` (exercise) | `WARMUP`, `WORKING`, `DROP`, `FAILURE` |
| `event category` | `health`, `social`, `work`, `travel`, `personal`, `family`, `media`, `education`, `maintenance`, `interaction`, `entertainment`, `other` |
| `significance` (event) | `routine`, `notable`, `major_milestone` |
| `completion_status` (entertainment) | `started`, `finished`, `abandoned`, `in_progress` |
| `entertainment_type` | `movie`, `tv_show`, `streaming`, `gaming`, `reading`, `podcast`, `live_performance` |
