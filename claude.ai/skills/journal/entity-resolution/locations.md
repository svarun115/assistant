# Entity Resolution — Locations

## Search Order

1. `query(entity="locations", where={"name": {"contains": "search_term"}})`
2. Search by place_id if known
3. Google Places search for public venues
4. Create only after confirming with user

## Relational Location Resolution

"[Person X]'s place/home" — follow this chain before escalating:

1. **Check person_residences:** Query residence history for Person X, use most recent `location_id`
2. **If no residence — scan past events:** `query(entity="events", where={"participants.name": {"contains": "<name>"}}, include=["location"], limit=50)` → filter to non-public locations. If found, also call `add_person_residence` to record it.
3. **Only escalate if both fail.**

## Public vs Private

| Type | Requires place_id | Examples |
|------|-------------------|----------|
| Public venue | YES (mandatory) | Restaurants, gyms, parks, offices, temples |
| Private residence | NO | Home, friend's house |
| Informal | NO | "Near the lake", "Somewhere in [Neighborhood]" |

**Gotcha:** For public venues always call `search_places()` first to get the `place_id`, then pass it when creating the location. Never create a public venue without a `place_id`.

Deduplication: if a location with the same place_id already exists, REUSE it. Never create duplicates.

## Generic Terms (home/office/gym)

**Never create literal "Home" or "Office" locations.** Resolution order:
1. Current narrative context (events in [City] → home = [City] home)
2. Same-day sleep anchor — query sleep events for date with location included
3. ±2 day sleep anchors
4. Owner residence history for the date range
5. Ask ONE question only if multiple plausible options remain

## Location Granularity

Do NOT create micro-locations ("desk", "counter", "living room") or cafeteria vendor names.

DO create parent location with details in title/notes: "[Company] Building 4 Cafeteria"
