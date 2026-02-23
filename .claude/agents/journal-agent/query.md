# Journal Agent — QUERY Mode

Reads from the journal. Two operations based on input:
- **`entities` provided** → resolve entities to DB IDs + fetch context briefs
- **`query_terms` provided** → semantic + structured search
- Both → run both in parallel

Read-only. No logging, no entity creation.

**Load on entry if not already in context from INIT:**
- `~/.claude/skills/journal/entities.md` — entity resolution rules, alias matching, phonetic variants
- `~/.claude/skills/journal/gotchas.md` — query field names, enum values

---

## Operation A: Entity Resolution

Follow `entities.md` for all resolution rules (cache-first lookup, DB queries, alias matching, phonetic variants, Generic Terms resolution order). After resolving, fetch a context brief for each resolved entity:

**Person brief** — run in parallel:
```
query(entity="events", where={participants.id: {eq: "<person_id>"}},
  orderBy="start", orderDir="desc", limit=3, include=["location", "participants"])

query(entity="person_notes", where={person_id: {eq: "<person_id>"}},
  orderBy="created_at", orderDir="desc", limit=5)
```
Also extract: relationship, category, birthday, known_since from person record.

**Location brief:**
```
query(entity="events", where={location_id: {eq: "<location_id>"}},
  orderBy="start", orderDir="desc", limit=3, include=["participants"])
```
Derive `typical_activities` from category + type fields of returned events.

**Exercise brief:**
```
query(entity="workouts", where={exercises.exercise_id: {eq: "<exercise_id>"}},
  orderBy="start", orderDir="desc", limit=3, include=["exercises"])
```
Extract last known weight/reps/sets from nested sets data.

Skip context brief if `include_context: false`. For ambiguous/unresolved, return candidates without fetching briefs.

### Return: QUERY_RESULT (entities)

```
entities:
  resolved:
    - raw: "Priya"
      type: person
      id: <uuid>
      canonical_name: "Priya Sharma"
      relationship: "colleague at Microsoft"
      source: db_query | cache
      brief:
        last_seen: "2026-02-10 — Lunch at Taj Bangalore (with Arun, Rohit)"
        recent_notes:
          - "Joining AWS Bangalore in March 2026" (career, 2026-01-15)
        health_flags: none

    - raw: "Balance gym"
      type: location
      id: <uuid>
      canonical_name: "Balance - The Club"
      brief:
        recent_visits:
          - "2026-02-22 — Pool swim + isometric leg work (with Acha)"
        typical_activities: "workouts (strength, swim)"

  ambiguous:
    - raw: "Indiranagar"
      candidates:
        - id: <uuid-1>, name: "Game Theory Indiranagar"
        - id: <uuid-2>, name: "Social, Indiranagar"
      action_needed: caller_must_pick

  unresolved:
    - raw: "Nikhil"
      context: "mentioned as squash partner"
      action_needed: create_or_skip

new_entities: { people: [{name, id, last_seen}], locations: [{name, id, last_seen}] }
```

---

## Operation B: Search

For each term in `query_terms`, run both shelves in parallel:

```
mcp__personal-journal__semantic_search(query: "<term>", limit: 10)
mcp__personal-journal__query(entity: "events", where: {title: {contains: "<key_word>"}}, limit: 10)
```

Merge, deduplicate by event ID, sort by date descending.

### Return: QUERY_RESULT (search)

```
search:
  terms: [list]
  results: N unique entries
  timeline:
    1. [DATE] "<event_title>" — <relevant_excerpt> (Event ID: <id>)
    ...
  summary: <2-3 sentence synthesis>
  cross_reference: <how this connects to query_context>
```
