# Verification Queries

SQL audit queries for data quality checks. Use selectively after processing.

> Replace `TARGET_DATE` with `YYYY-MM-DD`, `OWNER_ID` with journal owner UUID.
> All queries exclude soft-deleted records.

## 1. Participant Integrity (CRITICAL)

Social events must include owner as participant.

```sql
SELECT 
    e.id, e.title, e.start_time, e.event_type, e.category,
    (SELECT COUNT(*) FROM event_participants ep WHERE ep.event_id = e.id) as total_participants,
    EXISTS (
        SELECT 1 FROM event_participants ep 
        WHERE ep.event_id = e.id 
        AND ep.person_id = 'OWNER_ID'
    ) as has_owner
FROM events e
LEFT JOIN sleep_events se ON e.id = se.event_id
LEFT JOIN reflections r ON e.id = r.event_id
WHERE e.start_time::date = 'TARGET_DATE'
AND COALESCE(e.is_deleted,false) = false
AND e.deleted_at IS NULL
AND se.event_id IS NULL
AND r.event_id IS NULL
AND e.event_type != 'work'
ORDER BY e.start_time;
```

## 2. Event Location Completeness (CRITICAL)

Non-commute events need `location_id` (except if parent is commute).

```sql
SELECT 
    e.id, e.title, e.event_type, e.start_time, e.end_time
FROM events e
LEFT JOIN events parent
    ON parent.id = e.parent_event_id
    AND parent.deleted_at IS NULL
WHERE e.start_time::date = 'TARGET_DATE'
    AND e.deleted_at IS NULL
    AND COALESCE(e.is_deleted,false) = false
    AND e.event_type <> 'commute'
    AND e.location_id IS NULL
    AND NOT (parent.event_type = 'commute')
ORDER BY e.start_time;
```

## 3. Commute From/To Completeness (CRITICAL)

All commutes need both `from_location_id` and `to_location_id`.

```sql
SELECT 
    e.id AS event_id, e.title, e.start_time, e.end_time,
    c.transport_mode, c.from_location_id, c.to_location_id
FROM events e
JOIN commutes c ON c.event_id = e.id
WHERE e.start_time::date = 'TARGET_DATE'
    AND COALESCE(e.is_deleted, false) = false
    AND COALESCE(c.is_deleted, false) = false
    AND (c.from_location_id IS NULL OR c.to_location_id IS NULL)
ORDER BY e.start_time;
```

## 4. Location Quality

Public venues should have `place_id`.

```sql
SELECT l.canonical_name, l.location_type, l.place_id, e.title as used_in_event
FROM locations l
JOIN events e ON e.location_id = l.id
WHERE e.start_time::date = 'TARGET_DATE'
AND COALESCE(e.is_deleted,false) = false
AND e.deleted_at IS NULL
AND l.location_type NOT IN ('residence', 'private')
AND l.place_id IS NULL;
```

## 5. Work-Block Overlaps

Work blocks should not overlap with non-work events.

```sql
WITH work_blocks AS (
    SELECT id, title, start_time, end_time 
    FROM events 
    WHERE event_type = 'work'
      AND start_time::date = 'TARGET_DATE'
      AND COALESCE(is_deleted,false) = false
      AND deleted_at IS NULL
      AND end_time IS NOT NULL
), other_events AS (
    SELECT e.id, e.title, e.start_time, e.end_time, e.parent_event_id
    FROM events e
    WHERE e.start_time::date = 'TARGET_DATE'
      AND COALESCE(e.is_deleted,false) = false
      AND e.deleted_at IS NULL
      AND e.category != 'work'
      AND e.end_time IS NOT NULL
)
SELECT 
    w.title as work_event, w.start_time as work_start, w.end_time as work_end,
    o.title as overlapping_event, o.start_time as overlap_start, o.end_time as overlap_end
FROM work_blocks w
JOIN other_events o ON 
    (o.start_time >= w.start_time AND o.start_time < w.end_time) OR
    (o.end_time > w.start_time AND o.end_time <= w.end_time) OR
    (o.start_time <= w.start_time AND o.end_time >= w.end_time)
WHERE o.parent_event_id IS DISTINCT FROM w.id;
```

## 6. Dangling Sleep Blocks

Sleep events missing end_time or wake_time.

```sql
SELECT
    e.id, e.title, e.start_time, e.end_time,
    se.sleep_time, se.wake_time, e.created_at
FROM events e
JOIN sleep_events se ON se.event_id = e.id
WHERE e.deleted_at IS NULL
  AND COALESCE(e.is_deleted,false) = false
  AND (e.end_time IS NULL OR se.wake_time IS NULL)
ORDER BY e.start_time DESC
LIMIT 25;
```

## 7. Journal Entry Linkage

Verify raw journal entry exists for date.

```sql
SELECT entry_date, length(raw_text) as char_count 
FROM journal_entries 
WHERE entry_date = 'TARGET_DATE';
```

## 8. Specialization Coverage

Events that should be specialized but aren't.

```sql
SELECT 
    e.id, e.title, e.event_type, e.start_time,
    w.id as workout_id,
    m.id as meal_id,
    c.id as commute_id,
    ent.id as entertainment_id
FROM events e
LEFT JOIN workouts w ON e.id = w.event_id
LEFT JOIN meals m ON e.id = m.event_id
LEFT JOIN commutes c ON e.id = c.event_id
LEFT JOIN entertainment ent ON e.id = ent.event_id
WHERE e.start_time::date = 'TARGET_DATE'
AND e.deleted_at IS NULL
AND COALESCE(e.is_deleted,false) = false
ORDER BY e.start_time;
```

Red flags:
- Event titled like workout/meal/commute but no specialization row
- Specialization exists but key field missing
