# Travel & Commutes - Complete Reference

**Complete reference for travel and commute tracking: available tools, schema, query patterns, and extraction guide.**

---

## 1. 🎯 Quick Reference

### What Are Commutes?

Commutes are specialized events that capture travel between locations. They reference the events table for timing, with specialized data for routes, transport modes, and travel details.

### Available Travel Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| SQL queries | Get commute history, statistics, analytics | Via `execute_sql_query()` |
| `create_commute` | Create new commute events | Recording trips and travel |

### Transport Modes

- `driving` - Car, taxi, rideshare
- `public_transit` - Bus, train, subway, metro
- `walking` - On foot
- `cycling` - Bike, e-bike
- `flying` - Airplane
- `train` - Long-distance rail
- `ferry` - Boat, ferry
- `scooter` - E-scooter, skateboard
- `other` - Miscellaneous transport

---

## SQL Query Patterns for Commutes

**All commute queries use `execute_sql_query()`**

### Get Commute History
```sql
SELECT 
    c.id, c.transport_mode, e.start_time::date as commute_date,
    l_from.canonical_name as from_location,
    l_to.canonical_name as to_location,
    c.distance_km,
    EXTRACT(EPOCH FROM (e.end_time - e.start_time))/60 as duration_minutes,
    c.cost,
    c.traffic_condition,
    e.notes
FROM commutes c
JOIN events e ON c.event_id = e.id
LEFT JOIN locations l_from ON c.from_location_id = l_from.id
LEFT JOIN locations l_to ON c.to_location_id = l_to.id
WHERE e.start_time >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY e.start_time DESC;
```

### Get Commute Statistics
```sql
SELECT 
    c.transport_mode,
    COUNT(*) as count,
    ROUND(SUM(COALESCE(c.distance_km, 0))::numeric, 2) as total_distance_km,
    ROUND(AVG(COALESCE(c.distance_km, 0))::numeric, 2) as avg_distance_km,
    ROUND(SUM(COALESCE(c.cost, 0))::numeric, 2) as total_cost,
    ROUND(AVG(COALESCE(c.cost, 0))::numeric, 2) as avg_cost,
    ROUND(AVG(EXTRACT(EPOCH FROM (e.end_time - e.start_time))/60)::numeric, 2) as avg_duration_minutes
FROM commutes c
JOIN events e ON c.event_id = e.id
WHERE e.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.transport_mode
ORDER BY total_distance_km DESC;
```

### Get Route Statistics (From → To)
```sql
SELECT 
    l_from.canonical_name as from_location,
    l_to.canonical_name as to_location,
    c.transport_mode,
    COUNT(*) as trip_count,
    ROUND(AVG(COALESCE(c.distance_km, 0))::numeric, 2) as avg_distance_km,
    ROUND(AVG(COALESCE(c.cost, 0))::numeric, 2) as avg_cost,
    ROUND(AVG(EXTRACT(EPOCH FROM (e.end_time - e.start_time))/60)::numeric, 2) as avg_duration_minutes
FROM commutes c
JOIN events e ON c.event_id = e.id
LEFT JOIN locations l_from ON c.from_location_id = l_from.id
LEFT JOIN locations l_to ON c.to_location_id = l_to.id
WHERE e.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY l_from.canonical_name, l_to.canonical_name, c.transport_mode
ORDER BY trip_count DESC;
```

---

## 3. 🔄 Tool Usage Workflow

**Typical travel query workflow:**

1. **"How do I get around?"** → Use SQL: `GET commute statistics`
2. **"Show me my commutes"** → Use SQL: `GET commute history`
3. **"Show me route from X to Y"** → Use SQL with location filters
4. **"Show me [mode] trips"** → Use SQL with transport_mode filter
5. **"How much am I spending?"** → Use SQL: `GET commute statistics by mode`
6. **Record new trip** → Use `create_commute` write tool

**SQL-First Philosophy:** Use `execute_sql_query()` with the patterns above for all data retrieval.

---

## 4. Write Tool: `create_commute`

[Move to next section - write tool details]

---

## 5. 📝 Journal Extraction Guide

### Extraction Pattern

When extracting commute information from journal entries, identify:

1. **Event details (WHO, WHERE, WHEN)**
   - Start/end times
   - Origin and destination locations
   - Participants (if carpooling)
   - Event title and description

2. **Commute specifics (WHAT)**
   - Transport mode (driving, cycling, public_transit, etc.)
   - Distance (if mentioned)
   - Cost (if mentioned)
   - Traffic/weather conditions (in notes)

### Example Extractions

**Morning commute:**
```
Journal: "Drove to work this morning. Left at 8:15am, got there by 8:45am. Traffic was pretty light."

Event:
  event_type = 'commute'
  start_time = 08:15:00
  end_time = 08:45:00
  title = "Drive to office"
  notes = "Traffic was pretty light"
  tags = ['morning', 'work']

Commute:
  from_location_id = (Home)
  to_location_id = (Office)
  transport_mode = 'driving'
```

**Subway ride:**
```
Journal: "Took the Red Line to downtown at 9am. About 40 minutes."

Event:
  event_type = 'commute'
  start_time = 09:00:00
  end_time = 09:40:00
  title = "Subway to downtown"
  tags = ['morning', 'public_transit']

Commute:
  from_location_id = (Home)
  to_location_id = (Downtown)
  transport_mode = 'subway'
```

**Bike ride:**
```
Journal: "Biked to the gym at 6pm. Beautiful weather!"

Event:
  event_type = 'commute'
  start_time = 18:00:00
  title = "Bike ride to gym"
  notes = "Beautiful weather!"
  tags = ['evening', 'cycling', 'exercise']

Commute:
  from_location_id = (Home)
  to_location_id = (Gym)
  transport_mode = 'cycling'
```

**Carpool with friend:**
```
Journal: "Sarah gave me a ride to work at 8am."

Event:
  event_type = 'commute'
  start_time = 08:00:00
  title = "Carpool to office"
  tags = ['morning', 'carpool']

Commute:
  from_location_id = (Home)
  to_location_id = (Office)
  transport_mode = 'driving'

Participants: Sarah (role='driver')
```

### Inference Rules

**Transport mode from context:**
- "drove", "car" → `driving`
- "uber", "lyft", "rideshare" → `rideshare`
- "subway", "metro", "train" → `public_transit` or `subway`
- "walked" → `walking`
- "biked", "cycling" → `cycling`
- "flew", "flight" → `flying`
- Default for work commute → `driving`

**Location inference:**
- "to work", "to office" → Office location
- "home", "back home" → Home location
- "to gym", "to the gym" → Gym location

**Duration:**
- If not specified, compute from start_time and end_time
- If neither time specified, use reasonable defaults (e.g., 30 min for work commute)

---

## Important Notes

- Event with `event_type='commute'` MUST have commutes entry (enforced by trigger)
- Store brief route in event.title ("Drive to office")
- Store conditions in event.notes ("Heavy traffic")
- Use tags for context (`morning`, `rush_hour`, `delayed`)
- Multi-leg trips: Single commute with notes OR multiple events with parent_event_id
- Return trips: Create separate events for each direction

---

## Related Resources

- **EVENTS.md** - Event system architecture
- **LOCATIONS.md** - Location reference
