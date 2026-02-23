# Database Tool Cheatsheet

Critical gotchas and workflow patterns. Write and read tool schemas are self-documenting — this file covers only what the schemas don't tell you.

---

## Critical Gotchas

### Event-First Querying (Most Important Rule)

Workouts, meals, commutes, and entertainment are **event specializations**. They don't have their own date/time/location/participant fields — those live on the parent `events` entity.

**Rule:** To filter by date, time, location, or participants → query `events` with a `type` filter (e.g., `type: "workout"`). Use `include` to hydrate specialization data. Only query the child entity directly when filtering by specialization-specific fields.

**Valid filterable fields per entity:**

| Entity | Filterable Fields |
|--------|-------------------|
| `events` | `id`, `type`, `title`, `description`, `date`, `start`, `end`, `duration`, `location_id`, `category`, `significance`, `notes`, `tags` |
| `workouts` | `id`, `event_id`, `name`, `category`, `subtype`, `sport_type` |
| `meals` | `id`, `event_id`, `meal_title`, `meal_type`, `cuisine`, `portion_size` |
| `commutes` | `id`, `event_id`, `transport_mode`, `from_location_id`, `to_location_id` |
| `entertainment` | `id`, `event_id`, `entertainment_type`, `title`, `personal_rating`, `completion_status` |

**Common mistakes:**
- Querying `workouts` with `date >= X` — WRONG (`date` is not a field on workouts)
- Querying `events` with `start_time >= X` — WRONG (field is `start`, not `start_time`)
- Querying `commutes` with `date >= X` — WRONG (use `events` with `type: "commute"`)

---

### participant_ids REPLACES, Not Appends

`update_event(event_id, participant_ids=[...])` **replaces ALL participants**.

**Steps:**
1. Query current event with `include: ["participants"]`
2. Build complete list with changes
3. Pass the full list including existing + new

**Wrong:** Just passing the new person to add (removes everyone else!)

### Search Before Create (Always)

Before creating ANY entity (person, location, exercise), search first to prevent duplicates.

### place_id for Public Venues (Mandatory)

Always call `search_places()` first for public venues (restaurants, gyms, parks). Use the returned `place_id` when creating the location.

### Garmin Metrics Stay in Garmin

Do NOT copy Garmin stats (distance, pace, HR) into event notes or DB fields. Link via `external_event_id` + `external_event_source: "garmin"` and query Garmin when needed.

---

## Merge Workflows

### Merging Duplicate People

1. Identify canonical record (more events, has relationships)
2. Query events for the duplicate using `participants.name` filter
3. For EACH event: `update_event(event_id, participant_ids=[...])` replacing duplicate ID with canonical
4. Verify no events reference duplicate
5. `delete_person(person_id)` on the duplicate

### Merging Duplicate Exercises

1. `reassign_exercise_in_workouts(old_exercise_id, new_exercise_id)` — updates ALL workout references
2. `delete_exercise(exercise_id)` on the duplicate

---

## Health Condition Logging

### Query Before Logging Condition Updates

Before calling `log_health_condition_update`, always query for an existing log on that `(condition_id, log_date)`:
```
query(entity: "health_condition_logs", where: {condition_id: "<id>", log_date: "<date>"})
```
If a log already exists, use `update_health_condition_log` instead. Otherwise you'll hit a unique constraint violation.

### Don't Re-Fetch Garmin Summaries Already in Context

When fetching Garmin data for sleep-time lookups across day boundaries (e.g., backfilling Feb 11 and need Feb 12 sleep time), note that the adjacent day's summary is already available if previously fetched. Don't re-fetch the same date.

---

## Query Discipline

### Response Size Estimation

Before any query with `include`, estimate payload size: `rows x nested_objects x ~200 chars`.

**High-risk queries:**
- Workouts with `include: ["exercises"]` — each workout may have 5-10 exercises with 3-5 sets each. 50 workouts = 2000+ set objects = 100K+ chars.
- Events with multiple includes across a wide date range.

**Rules:**
- When querying workouts with exercises, **scope by date** or `limit < 15`
- If you need exercise data across many workouts, query the `exercises` catalog separately and join in-context by `exercise_id`
- Never query all historical workouts with full hydration

**If a query overflows:**
1. STOP — do NOT attempt to parse the overflow file
2. Re-query with tighter filters (narrower date range, fewer includes, lower limit)
3. Split into multiple smaller queries if needed
4. Three scoped queries are faster than fighting one oversized result

### Exercises Include — Fully Hydrated

`include: ["exercises"]` on the workouts entity returns `workout_exercises` rows with **nested exercise entity** (name, muscle_group, equipment) and **nested sets**. Each exercise row contains the full exercise details — no separate query needed for muscle group analysis.

### Two-Strike Bail-Out Rule

If the same tool/entity fails twice with similar errors, STOP and pivot immediately:

| Error Type | How to Recognize | Action |
|-----------|-----------------|--------|
| Server-side error | `column X does not exist`, internal query error | Report to user — likely an entity config mismatch |
| Overflow | Result too large for context | Re-query with tighter scope |
| Shell escaping | Dollar signs stripped, nested quotes broken | Write to `.js` or `.ps1` script file, then run it |
| Field validation | Returns `validFields` list | Use the suggested valid fields |

**Key distinction:** Field validation errors (which return `validFields`) are self-correctable in one retry. Server-side errors (missing columns, internal failures) are NOT — retrying with different field names is futile.

---

## Wrapper Tool Gotcha

### create_entertainment Requires event_type

`create_entertainment` does NOT auto-set `event_type` on the event dict (unlike `create_workout`/`create_meal`/`create_commute` which do). Always include `"event_type": "generic"` in the event object when using `create_entertainment`.

---

## Enum Quick Reference

Values sourced from current MCP tool schemas. When in doubt, check the tool definition.

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
