# Events - Complete Reference

**Foundation of the journal system: Events capture WHO, WHERE, WHEN for all activities. Specialized tools exist for workouts, meals, commutes, etc. Use `create_event` for generic activities.**

---

## Quick Reference

### When to Use This Resource

- **Specialized activities** (workouts, meals, commutes, entertainment) → Use their dedicated tools (see INSTRUCTIONS.md for domain map)
- **Generic activities** (meetings, social visits, appointments, communications) → Use `create_event` tool documented below
- **Cross-domain queries** → Use the event query tools below (work across all event types)

### Core Schema & Relationships
| Table | Purpose | Key Relationships |
|-------|---------|-------------------|
| `events` | The aggregate root | `location_id` (WHERE), `parent_event_id` (Hierarchy) |
| `event_participants` | Who was there | Links `events` ↔ `people` |
| `journal_entry_events` | Provenance | Links `events` ↔ `journal_entries` (Source text) |

### Event Query Tools (Work Across All Types)

**All event queries use SQL via `execute_sql_query()`**

| Query Type | SQL Pattern | When to Use |
|------------|------------|------------|
| Find events by participants | `SELECT * FROM events JOIN event_participants... WHERE person_id = ?` | "When did I last workout with Mike?" |
| Day summary | `SELECT * FROM events WHERE event_date = '2025-08-27' ORDER BY start_time` | "What did I do on August 27th?" |
| Parent events (hierarchical) | `SELECT * FROM events WHERE parent_event_id IS NULL ORDER BY start_time DESC` | "Show me my vacations this year" |
| Child events | `SELECT * FROM events WHERE parent_event_id = ? ORDER BY start_time` | "What did I do during that Europe trip?" |
| Create generic events | Write tool: `create_event` | When no specialized tool exists |

---

## Available Tools

### SQL Queries for Event Retrieval

**All event queries are read-only SELECT statements via `execute_sql_query()`**

#### Find Events by Participants
```sql
SELECT e.* 
FROM events e
JOIN event_participants ep ON e.id = ep.event_id
JOIN people p ON ep.person_id = p.id
WHERE p.canonical_name ILIKE '%Mike%'
  AND e.event_type ILIKE '%workout%'
ORDER BY e.start_time DESC;
```

#### Get Day Summary
```sql
SELECT 
    e.event_type,
    COUNT(*) as count,
    STRING_AGG(e.title, ', ') as titles
FROM events e
WHERE e.event_date = '2025-08-27'
  AND e.is_deleted = FALSE
GROUP BY e.event_type
ORDER BY e.start_time;
```

#### Find Parent Events (Hierarchical)
```sql
SELECT * FROM events 
WHERE parent_event_id IS NULL
ORDER BY start_time DESC;
```

#### Get Child Events
```sql
SELECT * FROM events 
WHERE parent_event_id = 'parent-uuid'
ORDER BY start_time;
```

### Write Tool: `create_event` ✍️
**Create standalone events (meetings, social visits, generic activities)**

**When to use:**
- Creating events from journal entries
- Recording meetings, appointments, social visits
- Any activity that doesn't need a specialized type (workout/meal/commute)

**Parameters:**
```json
{
  "title": "Team Meeting",                               // Required
  "description": "Weekly standup",                       // Optional
  "start_time": "2025-10-12T10:00:00",                  // Required (ISO 8601)
  "end_time": "2025-10-12T11:00:00",                    // Optional
  "event_type": "work",                                  // Optional: "generic", "communication", "work"
  "category": "work",                                    // Optional
  "significance": "routine",                             // Optional: "routine", "notable", "major_milestone"

  // Location (optional): provide a location_id (write tools accept only location_id)
  "location_id": "uuid-from-search-or-create_location",

  // Participants (optional): use EITHER names OR IDs
  "participant_names": ["Alice", "Bob"],                 // Auto-creates if needed
  // OR
  "participant_ids": ["uuid-1", "uuid-2"],              // Validates exist
  
  "notes": "Discussed Q4 roadmap",                       // Optional
  "tags": ["work", "team", "planning"]                   // Optional
}
```

**Dependency Chain:**
1. Location (optional): Validated via `location_id`
2. People (optional): Auto-created via `participant_names` OR validated via `participant_ids`
3. Event created with references

**Usage Patterns:**

**Pattern 1: Casual Creation (People Auto-Resolve, Location Omitted)**
```json
{
  "title": "Dinner with friends",
  "start_time": "2025-10-12T19:00:00",
  "participant_names": ["Alice", "Bob", "Charlie"],  // Creates people if needed
  "category": "social"
}
```

**Pattern 2: Precise Creation (Explicit IDs)**
```json
{
  "title": "Meeting at headquarters",
  "start_time": "2025-10-12T14:00:00",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",      // From search_locations
  "participant_ids": ["f47ac10b-58cc-4372-a567-0e02b2c3d479"], // From search_people
  "category": "work"
}
```

**Best Practices:**
- Use `participant_names` for quick entry (auto-creates people if needed)
- Use `location_id` when you have a UUID from `search_locations`/`create_location`
- Provide timestamps in ISO 8601 format (`YYYY-MM-DDTHH:MM:SS`)
- Don't mix names and IDs for the same entity type
- Search first if you think entity might exist (prevents duplicates)

**Error Handling:**
- Invalid UUID format → Error message with correct format
- Missing location/person ID → Error message suggesting entity doesn't exist
- Invalid timestamp → Error message with ISO 8601 format requirement

---

## Tool Usage

**Typical workflows:**
- "When did I last..." → Use SQL: Find Events by Participants
- "What did I do on [date]?" → Use SQL: Get Day Summary
- "Show me my vacations" → Use SQL: Find Parent Events
- "What happened during [trip]?" → Use SQL: Get Child Events

**SQL-First Philosophy:** Use `execute_sql_query()` with the patterns provided in the SQL Queries section above.

---

## Event Architecture

**Events capture:**
- **WHO**: Participants via `event_participants`
- **WHERE**: Location via `location_id`
- **WHEN**: Start/end times (auto-computes duration)
- **WHAT**: Specialization (workout/meal/commute tables or generic)

**Hierarchy:** Events nest via `parent_event_id` (Vacation → Trip → Activities)

---

## Journal Extraction

### Key Distinctions

**event_type vs category:**
- `event_type`: Structural (determines which table to join)
- `category`: Semantic (filtering/context)
- Example: `event_type='meal', category='work'` = business lunch

**parent_event_id vs source_event_id:**
- `parent_event_id`: Hierarchy (child is PART OF parent) - "Europe Trip" contains "Paris Flight"
- `source_event_id`: Provenance (where you LEARNED about it) - "Phone call" where you learned about someone else's workout

### Field Guidelines

**title**: Specific description - "Scrambled eggs and toast", "Leg day at gym", "Phone call with Mom"

**tags**: Lowercase with underscores, 3-7 typical - `['morning', 'post_workout', 'solo']`

**notes**: Qualitative observations - "Felt strong today", "Traffic was light"

**category**: Semantic grouping - `social`, `work`, `fitness`, `personal`, `family`

### Extraction Pattern

1. Identify if specialized type (workout/meal/commute/entertainment) → Use dedicated tool
2. If generic → Extract: title, start_time, participants, location, category, tags, notes
3. Use `create_event` (participants may auto-create via names; location requires `location_id` if provided)

### Example Extraction

```
Journal: "Had a video call with the product team at 2pm. Discussed Q4 roadmap."

create_event({
  title: "Product team video call",
  start_time: "2025-10-12T14:00:00",
  category: "work",
  participant_names: ["Alice", "Bob"],
  tags: ["video_call", "work", "product"],
  notes: "Discussed Q4 roadmap"
})
```

**Note:** For specialized activities (workouts, meals, commutes, entertainment), refer to their domain resources for dedicated tools and extraction patterns.

---

## Related Resources

- **WORKOUTS.md** - Workout events and tools
- **MEALS.md** - Meal events and tools
- **TRAVEL.md** - Commute events and tools
- **ENTERTAINMENT.md** - Entertainment events and tools
- **PEOPLE.md** - Participant management
- **LOCATIONS.md** - Location reference
