---
name: journal-garmin
description: Link workouts to Garmin activities and retrieve fitness metrics. Use for any workout or cardio activity (running, cycling, walking, hiking, swimming) to ensure proper Garmin linking.
---

# Garmin Workflow

Link workouts to Garmin and use Garmin as source of truth for fitness metrics.

## When to Link

**MANDATORY** for:
- Running, Cycling, Walking, Hiking, Swimming
- Any GPS-tracked cardio

**Optional** for:
- Strength training (if tracked)
- Yoga (if tracked)

**Skip** for:
- Activities not tracked on Garmin

## Linking Procedure

### Step 1: Query Garmin Activities

```
mcp_garmin_get_activities_by_date(
  start_date: "YYYY-MM-DD",
  end_date: "YYYY-MM-DD",
  activity_type: "running"  // optional
)
```

### Step 2: Match Criteria

| Signal | Tolerance |
|--------|-----------|
| Start time | ±15 minutes |
| Activity type | Must match |
| Distance | ±10% |
| Duration | ±10% |

### Step 3: Resolution

| Scenario | Action |
|----------|--------|
| Single confident match | Link automatically |
| Multiple matches | List candidates, ask user |
| No matches | Create unlinked, note "No Garmin match" |

### Step 4: Update Event

```json
{
  "event_id": "<uuid>",
  "external_event_source": "garmin",
  "external_event_id": "<garmin_activity_id>"
}
```

Use `mcp_personal_jour_update_event` with these fields.

## Data Retrieval

For linked workouts, always query Garmin for stats:

```sql
SELECT external_event_id FROM events 
WHERE id = '<uuid>' 
AND external_event_source = 'garmin';
```

Then:
```
activate_activity_data_tools()
mcp_garmin_get_activity(activity_id)
```

### Available Garmin Data

| Metric | Source |
|--------|--------|
| Distance | Garmin |
| Duration | Garmin |
| Pace/Speed | Garmin |
| Heart rate (avg, max, zones) | Garmin |
| Calories | Garmin |
| Elevation gain | Garmin |
| GPS route | Garmin |

## What NOT to Do

❌ **Don't copy Garmin stats to notes**
- Garmin is source of truth
- Stats in notes become stale

❌ **Don't assume DB columns exist**
- Only store `external_event_id` and `external_event_source`
- Verify schema before writing other fields

❌ **Don't skip Garmin lookup**
- Always attempt for cardio activities
- User shouldn't need to provide activity ID

❌ **Don't create duplicate links**
- Check if already linked before updating

## Timezone Handling

**CRITICAL:** Garmin timestamps are UTC.

```
Garmin: 2025-12-25T22:30:00Z (UTC)
User TZ: Asia/Kolkata (UTC+5:30)
Local: 2025-12-26T04:00:00 IST
→ This is a Dec 26 workout, not Dec 25!
```

Always convert before comparing dates.

## Audit Query

Find unlinked workouts:

```sql
SELECT e.id AS event_id, e.title, e.start_time, w.category, w.sport_type
FROM events e
JOIN workouts w ON e.id = w.event_id
WHERE e.external_event_id IS NULL
  AND w.category IN ('running', 'cycling', 'walking', 'hiking', 'swimming')
  AND e.start_time >= NOW() - INTERVAL '90 days'
  AND COALESCE(e.is_deleted, false) = false
ORDER BY e.start_time DESC;
```

## Error Handling

| Error | Action |
|-------|--------|
| Garmin API unavailable | Create unlinked, note failure |
| Activity not synced | Ask user to sync, retry later |
| Multiple matches | Present options, ask user |
| Wrong link | Update with correct ID |
