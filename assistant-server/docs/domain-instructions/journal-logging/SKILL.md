---
name: journal-logging
description: Process journal entries into structured records. Resolves people and locations, links workouts to Garmin, creates events with proper specializations. Use when user describes activities, meals, workouts, commutes, sleep, or experiences they want to log.
---

# Journal Logging

Process raw journal narratives into structured database records.

## Owner Context

- **Journal owner:** Varun Sashidharan
- Always include owner as participant on events they took part in
- Resolve owner via SQL: `SELECT id FROM people WHERE canonical_name = 'Varun Sashidharan'`

## Pre-Processing Checklist

When user says "Adding journal entry for [date]", **before** asking for narrative:

### 1. Fetch Garmin Context
```
mcp_garmin_get_activities_by_date(start_date, end_date)
mcp_garmin_get_user_summary(date)  # wake/sleep times, Body Battery, stress
```
Convert UTC timestamps to local timezone.

### 2. Fetch Gmail Context (Supporting Only)
```
mcp_gmail_search_emails(start_date, end_date, query: "receipt OR order")
```
Use as corroboration only. Never flag missing transactions.

### 3. Cache Owner ID
```sql
SELECT id FROM people WHERE canonical_name = 'Varun Sashidharan' LIMIT 1;
```

## Processing Steps

### Step 1: Parse the Narrative

Extract mentions of:
- **Times**: explicit ("at 7am") or relative ("morning", "after lunch")
- **People**: names, aliases, family terms
- **Locations**: specific venues, generic terms (home/office/gym)
- **Activities**: workouts, meals, commutes, entertainment, work blocks
- **Mood/Reflection**: feelings, insights, gratitude

### Step 2: Entity Resolution

**CRITICAL - Use the `journal-entities` skill for detailed procedures.**

Quick reference:
- Search by `canonical_name` AND `aliases`
- Query relationships to confirm identity
- For public venues: get `place_id` via Google Places first

### Step 3: Create Events

Order of creation:
1. **Sleep events** — use Garmin wake/sleep times if available
2. **Workout events** — link to Garmin activity ID (see `journal-garmin` skill)
3. **Meal events** — with participants and location
4. **Commute events** — with transport mode and stops
5. **Work events** — with work_type and productivity
6. **Entertainment events** — with ratings and completion status
7. **Generic events** — for anything else

### Step 4: Workout-Garmin Linking

**MANDATORY for cardio activities.** See `journal-garmin` skill for full procedure.

Quick reference:
1. Query Garmin for activities on that date
2. Match by start time + distance/duration
3. Set `external_event_source = 'garmin'`, `external_event_id = '<activityId>'`
4. Do NOT copy Garmin stats into notes

### Step 5: Log Raw Journal Entry

After creating structured events, store verbatim narrative:
```
mcp_personal_jour_log_journal_entry(date, raw_text, tags)
```

### Step 6: Post-Ingestion Verification

For half-day/full-day entries:
```sql
SELECT e.id AS event_id, e.title, e.event_type,
       w.id AS workout_id, m.id AS meal_id, c.id AS commute_id
FROM events e
LEFT JOIN workouts w ON e.id = w.event_id
LEFT JOIN meals m ON e.id = m.event_id  
LEFT JOIN commutes c ON e.id = c.event_id
WHERE e.start_time::date = '[date]'
  AND COALESCE(e.is_deleted, false) = false
ORDER BY e.start_time;
```

## Time Handling

- If time isn't explicit, do not invent it — ask
- Midnight-adjacent events may be spillover if user hasn't slept
- Garmin timestamps are UTC — convert to local before comparing

## Error Handling

| Error | Action |
|-------|--------|
| DB constraint violation | STOP, report, ask how to proceed |
| Entity not found | Ask 1 clarifying question |
| Garmin API error | Create unlinked workout, note failure |
| Ambiguous time | Ask for clarification |

## Output Format

```
Mode: LOG

Facts:
- Created X events (list types)
- Linked Y workouts to Garmin
- Participants: [names]
- Locations: [names]

Inferences:
- [Any assumptions made]

Questions (if any):
- [Max 1-3]
```

## Resource Files

For detailed procedures, see:
- [EXERCISE-RESOLUTION.md](EXERCISE-RESOLUTION.md) — Mandatory exercise dedup before workouts
- [SECONDHAND-EVENTS.md](SECONDHAND-EVENTS.md) — Events learned about, not witnessed
- [PITFALLS.md](PITFALLS.md) — Common edge cases and rules
