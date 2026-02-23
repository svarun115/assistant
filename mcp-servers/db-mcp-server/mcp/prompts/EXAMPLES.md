# Personal Journal MCP Server – Examples & Cheat Sheet

## 1. End-to-End Example
*User journal entry: “Ran 5 miles with Alex at the park. Felt sluggish again. Might be overtraining.”*

Processing sequence:
1. Save raw journal entry via `log_journal_entry` (stores in Postgres `journal_entries` AND indexes in Vector DB).
2. Resolve entities: Find person “Alex”; find location “park” (or create if absent).
3. Create structured workout event (+ participant Alex, location park, distance metadata). Event lives in `events` + `workouts`.
4. Link journal entry ↔ event (`journal_entry_events`).
5. Generate memory notes (optional):
   - Fact summary note: “5-mile run with Alex; sluggish” (importance 6).
   - Pattern note (if prior runs also sluggish): “Repeated post-run fatigue (3 sessions)” (importance 8).
6. Later question: “Why am I fatigued after runs?” → Fetch structured workouts (last N runs + intensity) AND perform semantic search (`search_journal_history`) for "fatigue after running". Combine: structured evidence + semantic context.
7. Respond citing sources: `Sources: events=[e123,e129,e137], memory=[m45,m52]`.

## 2. Quick Interaction Cheat Sheet
| User Says | Steps |
|-----------|-------|
| “Had coffee with Sarah at Blue Bottle.” | save_journal_entry → resolve Sarah & location → create generic event (social) → link entry ↔ event → optional memory note if new preference emerges |
| “Track my squat progress.” | SQL exercise progression query → analyze sets → optionally create summary memory note (“Squat volume rising last 4 weeks”) |
| “Why tired lately?” | Query recent sleep + workout intensity → fetch fatigue memory notes → combine, cite sources |

## 3. Common SQL Query Patterns

### Find Exercise Progression
```sql
SELECT 
    e.canonical_name AS exercise,
    w.set_number,
    s.reps,
    s.weight_kg,
    s.rpe,
    ev.start_time::date AS workout_date
FROM exercises e
JOIN workout_exercises we ON e.id = we.exercise_id
JOIN exercises_sets s ON we.id = s.workout_exercise_id
JOIN workouts w ON we.workout_id = w.id
JOIN events ev ON w.event_id = ev.id
WHERE e.canonical_name ILIKE '%Bench Press%'
  AND ev.start_time >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY ev.start_time ASC;
```

### Get Meals by Date Range
```sql
SELECT 
    e.start_time::date AS meal_date,
    m.meal_title,
    m.meal_type,
    SUM(fi.calories) AS total_calories,
    SUM(fi.protein_g) AS total_protein,
    l.canonical_name AS location
FROM meals m
JOIN events e ON m.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN food_items fi ON m.id = fi.meal_id
WHERE e.start_time >= '2025-01-01'
  AND e.start_time < '2025-02-01'
GROUP BY e.id, e.start_time, m.id, m.meal_title, m.meal_type, l.canonical_name
ORDER BY e.start_time DESC;
```

### Get Commute History
```sql
SELECT 
    c.commute_date,
    c.commute_type,
    l_from.canonical_name AS from_location,
    l_to.canonical_name AS to_location,
    c.distance_km,
    c.duration_minutes,
    c.vehicle_type,
    c.route_description
FROM commutes c
LEFT JOIN locations l_from ON c.from_location_id = l_from.id
LEFT JOIN locations l_to ON c.to_location_id = l_to.id
WHERE c.commute_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY c.commute_date DESC;
```

### Get Day Summary
```sql
SELECT 
    e.event_type,
    COUNT(*) AS count,
    STRING_AGG(e.title, ', ') AS titles
FROM events e
WHERE e.event_date = '2025-01-15'
  AND e.is_deleted = FALSE
GROUP BY e.event_type
ORDER BY count DESC;
```

### Find Person with Full Details
```sql
SELECT 
    p.id,
    p.canonical_name,
    p.aliases,
    p.relationship,
    p.birthday,
    COUNT(DISTINCT n.id) AS total_notes,
    MAX(n.note_date) AS last_note_date
FROM people p
LEFT JOIN person_notes n ON p.id = n.person_id
WHERE p.canonical_name ILIKE '%Sarah%'
  AND p.is_deleted = FALSE
GROUP BY p.id, p.canonical_name, p.aliases, p.relationship, p.birthday;
```
