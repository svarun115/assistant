# Entity Resolution Guide

Before creating ANY event, resolve all entities (people, locations, exercises). Prevents duplicates, ensures data integrity. Use the `query` tool for all searches. Soft-delete filtering is automatic.

---

## People Resolution

### Check user-context.md FIRST

The Family table in `user-context.md` has pre-resolved Journal IDs (UUIDs) and aliases for all close family and partner. If the person matches any name or alias there, use that UUID directly — **no DB query needed.**

### Voice Journaling & Typos

Journal entries are often voice-transcribed. Common phonetic errors: "Sharad" → "Sharath", "Tanya" → "Taneya". Strategy: search phonetically similar names, use context (workplace, recent events) to match. Do NOT add typos as aliases.

### Search Pattern (MANDATORY)

Every people search MUST search both canonical name AND aliases, include relationships:
```
query(entity="people", where={"name": {"contains": "search_term"}}, include=["relationships"])
```
If no results: `where={"aliases": {"contains": "SearchTerm"}}`

### Relational Resolution

When someone is described as "Dalwani's wife" or "Gauri's brother" — don't escalate. Instead:
1. Get anchor person's UUID from cache or DB
2. Query their relationships: `query(entity="people", where={"id": {"eq": "<uuid>"}}, include=["relationships"])`
3. Match relationship type and use that person's ID

Escalate only if anchor has no matching relationship type, or multiple same-type matches.

### Family Terms (Amma/Appa/Mom/Dad)

Context-dependent: if narrative mentions Gauri's family, "Amma/Appa" = Gauri's parents, not owner's. Default to owner's parents only if clearly about their family. When uncertain: "When you say 'Appa', do you mean your father or Gauri's father?"

### Relationship Graph Traversal

"How is X related to me?" — traverse up to 3 hops. Present path: "Lekshmy → Gauri's mother → your mother-in-law." Only ask if no path found.

### Duplicate Detection

Multiple records for same person → check which has relationships/event history (that's canonical). Flag: "Found both 'Vaish' and 'Vaishnavi Sashidharan' — using the one with event history." Never silently pick one.

### Merging Duplicate People

1. Identify canonical record (more data/relationships/recent activity)
2. Query events with duplicate using `participants.name` filter
3. For EACH event: `update_event(event_id, participant_ids=[...])` with canonical ID
4. Verify no events reference duplicate
5. `delete_person(person_id)` on duplicate

### Presenting People

**Never show UUIDs.** Always: "Gauri Pillai (your wife)", "Mohit (colleague at Microsoft)"

### Creating New People

Before creating, MUST have: searched by name and aliases, searched semantically for typos/variants, presented findings to user, received explicit confirmation.

Placeholder for unnamed relatives: `<Person>'s Mother (name unknown)`, alias `<Person>'s mom`. Create relationship immediately.

### Personal History Capture

| Fact Type | Tool | Required Fields |
|-----------|------|-----------------|
| Education | `add_person_education` | institution, location_id, dates |
| Work | `add_person_work` | employer, role, location_id, dates |
| Residence | `add_person_residence` | location_id, temporal dates |

`person_notes` may supplement but must NOT be the only record for structured facts.

---

## Location Resolution

### Search Order

1. `query(entity="locations", where={"name": {"contains": "search_term"}})`
2. Search by place_id if known
3. Google Places search for public venues
4. Create only after confirming with user

### Relational Location Resolution

"[Person X]'s place/home" — follow this chain before escalating:

1. **Check person_residences:** Query residence history for Person X, use most recent `location_id`
2. **If no residence — scan past events:** `query(entity="events", where={"participants.name": {"contains": "<name>"}}, include=["location"], limit=50)` → filter to non-public locations. If found, also call `add_person_residence` to record it.
3. **Only escalate if both fail.**

### Public vs Private

| Type | Requires place_id | Examples |
|------|-------------------|----------|
| Public venue | YES (mandatory) | Restaurants, gyms, parks, offices, temples |
| Private residence | NO | Home, friend's house |
| Informal | NO | "Near the lake", "Somewhere in Koramangala" |

Deduplication: if a location with the same place_id already exists, REUSE it.

### Generic Terms (home/office/gym)

**Never create literal "Home" or "Office" locations.** Resolution order:
1. Current narrative context (events in Trivandrum → home = Trivandrum home)
2. Same-day sleep anchor (where did they sleep?)
3. ±2 day sleep anchors
4. Owner residence history for the date range
5. Ask ONE question only if multiple plausible options remain

### Location Granularity

Do NOT create micro-locations ("desk", "counter", "living room") or cafeteria vendor names ("Sodexo"). DO create parent location with details: "Microsoft Building 4 Cafeteria".

---

## Exercise Resolution

### Common Duplicate Traps

- "Pull Up" vs "Pull-up" (hyphenation)
- "Calve Raises" vs "Calf Raises" (spelling)
- "Lateral Lunges" vs "Lateral Lunge" (plural)
- "Kettlebell Row" vs "Row" (equipment prefix)

Search: `query(entity="exercises", where={"name": {"contains": "row"}})`

### Equipment is Variation, NOT Identity

Correct: one "Row" exercise with `equipment: ["barbell", "dumbbell", "cable", "kettlebell"]`

Wrong: separate exercises for each equipment variant.

Exception: different movement patterns ARE different exercises (Incline vs Flat Bench Press).

If an equipment variant is missing, update the existing exercise first: `update_exercise(exercise_id, equipment=[...existing, "kettlebell"])`, then use that ID.

### Canonical Naming

Singular form, general name, standard hyphenation: "Lateral Lunge", "Row", "Pull-up". No combos — "Tabata: X + Y" → two separate exercises.

### Pre-Workout Audit (MANDATORY)

Before `create_workout`: list EVERY exercise from narrative, resolve ALL (search + create missing), verify each ID exists and isn't deleted, build complete workout. Never put unresolved exercises in notes.

---

## Entity Resolution Gate (LOG Mode — MANDATORY)

### Phase 1: Discovery (read-only)

- Search all people mentioned
- Search all locations mentioned
- Search all exercises (for workouts)

### Phase 2: Present Summary and Wait

```
Entity Resolution for [DATE]

People — Resolved:
| Narrative | Match             | Relationship       |
| Gauri     | Gauri Pillai      | Wife               |
| Amma      | Lekshmy C.        | Gauri's mother     |

People — NOT FOUND:
| Name  | Context          | Action                       |
| Priya | "met at cafe"    | Create? (colleague/friend?)  |

Locations — Resolved:
| Narrative | Match            |
| KBR Park  | KBR National Park |

Should I proceed with these resolutions?
```

**WAIT for user confirmation before Phase 3.**

### Phase 3: Creation (only after confirmation)

1. Create confirmed new entities
2. Create events with resolved IDs
3. Log raw journal entry to semantic shelf
