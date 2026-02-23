# Entity Resolution Guide

## Overview

Before creating ANY event, you MUST resolve all entities (people, locations, exercises). This prevents duplicates and ensures data integrity.

Use the `query` tool for all resolution searches. Soft-delete filtering is automatic.

---

## People Resolution

### User Context Cache (Check FIRST — Skip DB Query)

Before querying the DB, read `~/.claude/data/user-context.md`. The **Family** table there contains pre-resolved Journal IDs (UUIDs) and aliases for all close family and partner.

**Rule:** If the person matches any name or alias in that table, use that UUID directly — **no DB query needed.**

### Voice Journaling & Typos

Journal entries are often voice-transcribed, leading to phonetic errors:
- "Sharad" → "Sharath"
- "Tanya" → "Taneya"
- "Nehru" → "Ranju"

**Resolution strategy:**
1. Search for phonetically similar names in the DB
2. Use context (workplace, relationship, recent events) to match
3. Correct typos in the raw journal file
4. Do NOT add typos as aliases — they're errors, not alternate names

### Search Pattern (MANDATORY)

Every people search MUST search both canonical name AND aliases, and include relationship context:

```
query(entity="people", where={"name": {"contains": "search_term"}}, include=["relationships"])
```

If no results, also try alias search: `where={"aliases": {"contains": "SearchTerm"}}`

### Relational People Resolution (BEFORE ESCALATING)

When a person is described relationally — e.g., "Dalwani's wife", "Gauri's brother", "Appa's colleague" — AND the anchor person (Dalwani, Gauri, etc.) is a known entity:

**Do NOT escalate as ambiguous. Instead:**
1. Get the anchor person's UUID from cache or DB
2. Query their relationships: `query(entity="people", where={"id": {"eq": "<anchor_uuid>"}}, include=["relationships"])`
3. Match the relationship type (spouse → wife/husband, sibling → brother/sister, etc.)
4. Use the matched person's ID

Only escalate if: (a) the anchor person has no matching relationship type, or (b) there are multiple matches with the same relationship type.

### Family Terms (Amma/Appa/Mom/Dad)

**Context-dependent resolution:**
- If narrative mentions people from a specific family (e.g., Gauri's family: Vijay, Paru, Dhruv), interpret "Amma/Appa" as belonging to THAT family
- Only default to the owner's parents if context is clearly about their family or they are alone
- When uncertain, ask: "When you say 'Appa', do you mean your father or Gauri's father?"

### Relationship Graph Traversal

When asked "how is X related to me?" and no direct relationship exists:
1. Query relationships FROM the owner (see `~/.claude/data/user-context.md` for owner identity and Journal Person ID)
2. Query relationships TO the person
3. Traverse up to 3 hops to find connection
4. Present the path: "Lekshmy → Gauri's mother → your mother-in-law"

Only ask if no path exists or multiple equally-plausible paths exist.

### Duplicate Detection

If search returns multiple records that appear to be the same person:
- Check which has relationships, event history (that's the canonical one)
- Flag the duplicate: "Found both 'Vaish' and 'Vaishnavi Sashidharan' with alias 'Vaish' — using the one with event history"
- Do NOT silently pick one

### Merging Duplicate People (CRITICAL WORKFLOW)

When you identify duplicate person records:

**Step 1: Identify the canonical record**
- Query both records — the one with MORE data/relationships/recent activity is typically canonical
- If user confirms they're the same person, proceed with merge

**Step 2: Find all events with the OLD (duplicate) ID**
- Query events with `participants.name` matching the duplicate

**Step 3: For EACH event, update participants to use NEW (canonical) ID**
- Get current participant list for the event
- Replace old ID with new ID in the array
- Use `update_event(event_id, participant_ids: [<new-array>])`

**Step 4: Soft-delete the old duplicate record**
- Use `delete_person(person_id: <OLD-DUPLICATE-ID>)`

**IMPORTANT:** Do NOT skip steps. The `update_event` tool handles participant reassignment.

### Presenting People to User

**NEVER show UUIDs.** Always present as:
- "Gauri Pillai (your wife)"
- "Lekshmy Chidambaram (Gauri's mother, your mother-in-law)"
- "Mohit (colleague at Microsoft)"

### Creating New People

Before creating, you MUST have:
1. Searched by name and aliases
2. Searched semantically for typos/variants
3. Presented findings to user
4. Received explicit confirmation

**Placeholder pattern for unnamed relatives:**
- Canonical name: `<Person>'s Mother (name unknown)`
- Alias: `<Person>'s mom`
- Create relationship immediately

### Personal History Capture

When user mentions biographical facts, use dedicated tools:

| Fact Type | Tool | Required Fields |
|-----------|------|-----------------|
| Education | `add_person_education` | institution, location_id, dates |
| Work | `add_person_work` | employer, role, location_id, dates |
| Residence | `add_person_residence` | location_id, temporal dates |

**Rule:** `person_notes` may supplement but must NOT be the only record for structured facts.

---

## Location Resolution

### Search Order

1. Search by name: `query(entity="locations", where={"name": {"contains": "search_term"}})`
2. Search by place_id if known
3. Google Places search for public venues
4. Create only after confirming with user

### Relational Location Resolution (BEFORE ESCALATING)

When a location is described as "[Person X]'s place/home/house/flat" — AND Person X is a known entity:

**Do NOT escalate as "not found". Follow this 3-step chain:**

**Step 1: Check person_residences table**
Query residence history for Person X using their UUID. Use the most recent (or current) residence `location_id`.

**Step 2: If no residence record — scan past events (MANDATORY before escalating)**
Search for past events where Person X was a participant at a residential location:
```
query(entity="events", where={"participants.name": {"contains": "<person_name>"}}, include=["location"], limit=50)
```
Filter results to events at non-public locations (residence, apartment, house type). Any location found this way is likely their home — use it.

If the location is found via past events but is missing from `person_residences`, also call `add_person_residence` with:
- `person_id`: Person X's UUID
- `location_id`: the found location's UUID
- `start_date`: estimated (ask user if known, or use earliest event date as proxy)
- `is_current`: true (unless context suggests otherwise)

**Step 3: Only escalate if Steps 1 and 2 both fail** (truly no residential location found in DB for this person).

### Public vs Private

| Type | Requires place_id | Examples |
|------|-------------------|----------|
| Public venue | YES (mandatory) | Restaurants, gyms, offices, parks, temples |
| Private residence | NO | Home, friend's house, family home |
| Informal location | NO | "Near the lake", "Somewhere in Koramangala" |

### Deduplication by place_id

If a location with the same place_id already exists, REUSE it. Never create duplicates.

### Generic Terms (home/office/gym)

**Never create literal "Home" or "Office" locations.**

Resolution order:
1. **Current narrative context** — If day's events are in Trivandrum, "home" = Trivandrum home
2. **Same-day sleep anchor** — Where did they sleep? Query sleep events for the date with location included
3. **±2 day sleep anchors** — Pattern from nearby days
4. **Owner residence history** — Query person residences for the date range
5. **Ask ONE question** — Only if multiple plausible options remain

### Location Granularity

**Do NOT create:**
- Micro-locations: "desk", "counter", "living room"
- Vendor names in cafeterias: "Sodexo", "Melopedia"

**DO create:**
- Parent location with details in title/notes: "Microsoft Building 4 Cafeteria"

---

## Exercise Resolution

### The Duplicate Problem

Common mistakes that create duplicates:
- "Pull Up" vs "Pull-up" (hyphenation)
- "Calve Raises" vs "Calf Raises" (spelling)
- "Lateral Lunges" vs "Lateral Lunge" (plural)
- "Kettlebell Row" vs "Row" (equipment prefix)

### Search Pattern

Search by name and variants: `query(entity="exercises", where={"name": {"contains": "row"}})`

### Equipment is Variation, NOT Identity

**Correct:** One "Row" exercise with equipment array: `["barbell", "dumbbell", "cable", "kettlebell"]`

**Wrong:** Separate exercises for "Barbell Row", "Dumbbell Row", "Kettlebell Row"

**Exception:** Different movement patterns ARE different exercises (e.g., "Incline Bench Press" vs "Flat Bench Press")

### If Equipment Variant Missing

Update existing exercise first:
```
update_exercise(exercise_id, equipment=[...existing, "kettlebell"])
```

Then use that exercise ID.

### Canonical Naming Rules

- Singular form: "Lateral Lunge" not "Lunges"
- General name: "Row" not "Kettlebell Row"
- Standard hyphenation: "Pull-up" (hyphenated)
- No combos: "Tabata: X + Y" → log as two separate exercises

### Pre-Workout Audit (MANDATORY)

Before calling `create_workout`:
1. List EVERY exercise from the narrative
2. Resolve ALL of them (search + create missing)
3. Verify each ID exists and isn't soft-deleted
4. Build complete workout with all exercises
5. ONLY THEN call create_workout

**Never:** "I found 5 of 10 exercises, I'll put the rest in notes" — WRONG

---

## Entity Resolution Gate (MANDATORY for LOG mode)

Before creating ANY events:

### Phase 1: Discovery (read-only)

- Search all people mentioned
- Search all locations mentioned
- Search all exercises (for workouts)

### Phase 2: Present Summary

```
**Entity Resolution for [DATE]**

**People — Resolved:**
| Name (narrative) | Match | Relationship |
|------------------|-------|--------------|
| Gauri | Gauri Pillai | Wife |
| Amma | Lekshmy Chidambaram | Gauri's mother |

**People — NOT FOUND:**
| Name | Context | Action |
|------|---------|--------|
| Priya | "met Priya at cafe" | Create new (colleague? friend?) |

**Locations — Resolved:**
| Name | Match | Type |
|------|-------|------|
| KBR Park | KBR National Park | park |

Should I proceed with these resolutions?
```

### Phase 3: Creation (ONLY after user confirms)

1. Create confirmed new entities
2. Create events with resolved entity IDs
3. Log raw journal entry to semantic shelf
