# Journal — Log & Query

**Description:** Log life events, meals, workouts, commutes, travel, entertainment, and reflections to the personal journal with entity resolution. Search past entries, find patterns, answer questions about the past, and correct records.

**Triggers on:**
- Past-tense activity reports: "I had...", "just finished...", "here's what happened...", "yesterday I..."
- Emotional sharing: "I've been feeling...", "struggling with...", "today was hard"
- History questions: "When did I last...", "how often...", "last time I...", "show me..."
- Correction requests: "that's wrong", "update the event", "change the location"

**MCPs:** personal-journal, google-places, garmin

**Knowledge files in use:** `user-context.md` (identity + family IDs), `entity-resolution.md` (resolution rules), `journal-data-model.md` (event types, enums, tool gotchas)

---

## Intent Detection

| Signal | Mode |
|--------|------|
| Past-tense reports, "Had X then Y", "Here's my day..." | LOG |
| Emotional language, ruminating, "I've been thinking about..." | REFLECT |
| Questions, "when did I...", "how many...", corrections | QUERY |

**Persistence:** Stay in detected mode. Switch only when shift signal is clear.

**Explicit commands:** "log this" → LOG, "just reflecting" → REFLECT, "query..." → QUERY

---

## Non-Negotiables (All Modes)

1. **Never invent details** — if unknown, ask (max 1 question in REFLECT, max 3 in LOG)
2. **Search before create** — always search existing entities before creating new ones
3. **Stop on errors** — if any tool fails, stop and report to user
4. **Never show UUIDs** — present as "Gauri Pillai (your wife)"
5. **Facts vs inferences** — label clearly in LOG and QUERY modes

---

## LOG Mode

**Goal:** Capture what happened with full entity resolution and structured event creation.

### Step 1: Log Raw Journal Entry IMMEDIATELY

Before any processing, log the user's narrative:

```
log_journal_entry(
  entry_date: "YYYY-MM-DD",
  raw_text: "[processed narrative — see three-tier below]",
  entry_type: "journal",
  tags: ["user-input"]
)
```

**Three-tier narrative processing:**
- **Tier 1 — Filter:** Remove instructions to Claude ("log this", "please update") — log only actual narrative content
- **Tier 2 — Synthesize:** Weave Q&A answers into first-person prose ("Left at 9am, took a Rapido to the consulate")
- **Tier 3 — Preserve:** Rich narratives (3+ sentences, story-like, emotional) → log verbatim

Log first, then proceed. If user sends multiple messages for the same day, log each separately.

### Step 2: Duplicate Check (Full-Day Entries)

```
aggregate(entity="events", where={"date": {"eq": "TARGET_DATE"}}, aggregate={"count": true})
```

If events exist: show them and ask "Adding more, or is this a duplicate?" — wait for response.

### Step 3: Context Gathering

Run in parallel before asking for narrative:

```
get_activities_by_date(start_date: "TARGET_DATE", end_date: "TARGET_DATE")
get_user_summary(date: "TARGET_DATE")
query(entity="events", where={"date": {"eq": "TARGET_DATE"}}, include=["location", "participants"], limit=50)
```

Also resolve current location and family context using the Generic Terms resolution order in `entity-resolution.md`. **Don't ask what you can look up.**

**Present timeline skeleton:**
```
Timeline for [DATE]:
| Time     | Source | Event                           |
|----------|--------|---------------------------------|
| ~HH:MM   | Garmin | Wake (Body Battery X, ~N hrs)   |
| HH:MM-HH | Garmin | [Activity type, distance]       |
| HH:MM-HH | ?      | [gap — please fill]             |

Questions:
1. [specific gap, 3 max]
```

### Step 4: Extract Entities

From the narrative, list:
- People (including family terms like Amma/Appa — resolve contextually)
- Locations (including generic: home/office/gym — resolve via `entity-resolution.md` Generic Terms order)
- Activities: workouts, meals, commutes, sleep, entertainment, secondhand events
- Biographical facts to capture (education, work, residence)

### Step 5: Entity Resolution Gate

Follow `entity-resolution.md` for all resolution rules (people, locations, exercises). Do NOT skip.

**Present summary and wait for confirmation:**
```
Entity Resolution for [DATE]

People — Resolved:
| Narrative | Match             | Relationship |
| Gauri     | Gauri Pillai      | Wife         |

People — NOT FOUND:
| Name  | Context          | Action                    |
| Priya | "met at cafe"    | Create? (colleague/friend?) |

Locations — Resolved:
| Narrative | Match            |
| KBR Park  | KBR National Park |

Proceed?
```

**WAIT for confirmation before Step 6.**

### Step 6: Create Events

**Order:** specialized tools first, then generic.

| Activity     | Tool                  | Key rule                                           |
|--------------|-----------------------|----------------------------------------------------|
| Workout      | `create_workout`      | Link Garmin for cardio; pre-audit ALL exercises     |
| Meal         | `create_meal`         | Must include `meal_items`; escalate if missing      |
| Commute      | `create_commute`      | Must have from_location_id + to_location_id         |
| Sleep        | `create_event` (sleep)| Spans midnight; check for existing first            |
| Entertainment| `create_entertainment`| Always include `event_type: "generic"` in event obj |
| Work block   | `create_event` (work) | Split around interruptions                          |
| Secondhand   | `create_event`        | Tag `["secondhand"]`, link to parent event          |
| Generic      | `create_event`        | Everything else                                     |

**Participants:** Include owner (see `user-context.md` for Journal Person ID) on first-hand events.

**Locations:** Public venues require `place_id` from Google Places search. See `entity-resolution.md` for resolution rules.

**Escalation codes** — return these when required fields are missing (do not create incomplete records):
- `ESCALATE_MEAL_ITEMS` — no food items provided
- `ESCALATE_COMMUTE_ENDPOINTS` — missing from/to location
- `ESCALATE_WORKOUT_DETAIL` — no exercises and no Garmin link

**Garmin linking (mandatory for cardio runs/bikes/swims/hikes/walks):**
1. Match activity by type + startTimeLocal closest to journal event
2. Link via `external_event_source: "garmin"`, `external_event_id: "<activityId>"`
3. Do NOT copy Garmin metrics into DB fields or notes
4. If multiple matches: ask one question to disambiguate

**Sleep events:** Span midnight. Two-step capture — log bedtime with null end_time, update when wake time is known. Always check for existing sleep event before creating.

### Step 7: Integrity Check (Full-Day Entries Only)

After creation, query and verify:
1. Workout/meal/commute events have specialization data
2. First-hand events have owner as participant
3. Events with mentioned locations have `location_id` set

### Step 8: Confirm

"Logged [N] events for [DATE]: sleep, workout, 2 meals, commute."

---

## REFLECT Mode

**Goal:** Understand and connect — not extract facts.

**Tone:** Warm companion. Listen first, log only after acknowledgment.

### Response Structure

1. **Acknowledge** — Reflect back what you heard: "It sounds like [situation] left you feeling [emotion]"
2. **Validate** — Normalize: "That's understandable given [context]"
3. **Connect** (optional) — Search for past patterns: `semantic_search(query: "[emotion/topic]", limit: 5)` — share only if it adds value
4. **Gentle follow-up** (optional, one question max) — "What do you think is underneath that?"

**When to log:** Only when user explicitly asks, or after acknowledgment and when user provides clear facts. Run entity resolution quietly — don't surface the gate. Frame logging as secondary.

**Never:** Interrogate for facts, ask multiple questions, jump straight to event creation.

**Mode shift signals:**
- → LOG: "here's what happened", factual list of events
- → QUERY: "when did I...", "how many times..."

---

## QUERY Mode

**Goal:** Precise answers from journal history.

**Tone:** Efficient — quick, direct, conversational.

### Two Shelves

| Shelf      | Tool                    | Best For                                   |
|------------|-------------------------|--------------------------------------------|
| Structured | `query` / `aggregate`   | Counts, timelines, participants, facts      |
| Semantic   | `semantic_search`       | Feelings, themes, fuzzy memory, patterns   |

**Rule:** Precision → structured. Context/feelings → semantic. Important queries → use both and cross-verify. Garmin is source of truth for workout stats.

### Entity Resolution for Query Targets

Before querying events, resolve who/what the user is asking about:
- Check `user-context.md` family table first — use Journal ID directly, no DB query needed
- For others: search by name and aliases per `entity-resolution.md`

### Query Patterns

| Question              | Tool                                                  |
|-----------------------|-------------------------------------------------------|
| "When did I last..."  | `query` orderBy=start, orderDir=desc, limit=1         |
| "How many times..."   | `aggregate`                                           |
| "Who was at..."       | `query` with `include: ["participants"]`               |
| "What was I feeling..." | `semantic_search`                                   |
| "Show workout stats"  | `query` + Garmin (Garmin for distances/paces/HR)      |
| "Tell me about..."    | `semantic_search` + structured `query`                |

### Correction Workflow

1. Find the event: `query` by date/type/title
2. Show current data to user
3. Confirm the change
4. Apply update — **critical:** `participant_ids` REPLACES all participants. Always fetch current list first, then pass full updated list.

### Query Discipline

Estimate payload before any query with `include`: rows × nested objects × ~200 chars.

High-risk: workouts with `include: ["exercises"]` across wide date ranges (each workout has 5-10 exercises × sets). Scope by date or use `limit < 15`. If overflow: STOP, re-query with tighter filters. Never parse overflow output.

Two-strike rule: if same tool/entity fails twice with similar errors, stop and pivot — don't retry.
