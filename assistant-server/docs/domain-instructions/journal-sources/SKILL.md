---
name: journal-sources
description: Data source trust hierarchy and conflict resolution. Use when sources disagree or need to decide which data to trust (Garmin vs user stated, Gmail vs journal, etc).
---

# Source Priority Rules

Which data source to trust when sources conflict.

## Source Hierarchy

### Workout/Fitness Data

| Data Point | Primary | Fallback |
|------------|---------|----------|
| Distance | Garmin | User stated |
| Duration | Garmin | User stated |
| Pace/Speed | Garmin | Calculate |
| Heart Rate | Garmin | N/A |
| Calories | Garmin | N/A |
| Elevation | Garmin | N/A |
| Workout Type | User stated | Garmin |
| Context/Notes | User journal | N/A |

**Rule:** Garmin wins for metrics. User wins for context.

### Sleep Data

| Data Point | Primary | Fallback |
|------------|---------|----------|
| Sleep/Wake time | Garmin | User stated |
| Sleep quality | User perception | Garmin score |
| Interruptions | User recall | Garmin |
| Dream content | User journal | N/A |

### Location Data

| Data Point | Primary | Fallback |
|------------|---------|----------|
| Venue name | Google Places | User stated |
| Address | Google Places | N/A |
| Place ID | Google Places | N/A |
| Visit time | User journal | Gmail receipt |
| Who was there | User journal | N/A |

### Time/Schedule Data

| Data Point | Primary | Fallback |
|------------|---------|----------|
| Workout start/end | Garmin (local) | User stated |
| Meal time | User stated | Gmail receipt |
| Commute time | User stated | Uber receipt |
| Event time | User stated | Calendar |

### People Data

| Data Point | Primary | Fallback |
|------------|---------|----------|
| Identity | DB (name + aliases) | Ask user |
| Relationship | DB (relationships) | Never assume |
| Presence | User stated | Never assume |

## Conflict Resolution Protocol

When sources disagree:

1. **State both values:**
   > "Your journal says 8K, Garmin shows 7.2K."

2. **Label the discrepancy:**
   > "~10% difference, possibly GPS accuracy."

3. **Ask which to trust:**
   > "Which should I use?"

4. **Record decision:**
   - Use chosen value
   - Optionally note discrepancy

### Common Scenarios

| Scenario | Resolution |
|----------|------------|
| User "ran 10K", Garmin 9.8K | Prefer Garmin |
| User "woke 7am", Garmin 6:45am | Ask user |
| User "Thai restaurant", Places "Thai Kitchen" | Use Places name |
| Gmail 8pm dinner, user says 7:30pm | Prefer user |

## Never Assume

These require explicit user input:
- Who was at an event
- Relationships between people
- Whether activity happened (even with receipt)
- How user felt
- Why something happened

## Timezone Rules

| Source | Timezone | Action |
|--------|----------|--------|
| Garmin | UTC | Convert to local |
| Gmail | Varies | Check headers |
| User input | Local | Use as-is |
| DB storage | UTC | Convert for display |

**Default:** Assume user's local timezone unless specified.

## Query Pattern for Conflicts

```sql
-- Get DB value
SELECT e.title, e.external_event_id, w.category, w.sport_type
FROM events e
JOIN workouts w ON e.id = w.event_id
WHERE e.id = '<uuid>';
```

If `external_event_id` exists:
```
mcp_garmin_get_activity(external_event_id)
```

Compare and present both if different.
