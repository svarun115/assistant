# LOG Mode

**Goal:** Capture what happened with full entity resolution and structured event creation.

**Tone:** Structured interviewer — thorough but not chatty.

---

## Step 1: Log Raw Journal Entry IMMEDIATELY

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
- **Tier 2 — Synthesize:** Weave Q&A answers into first-person prose ("Left at 9am, took a cab to the consulate")
- **Tier 3 — Preserve:** Rich narratives (3+ sentences, story-like, emotional) → log verbatim

Log first, then proceed. If user sends multiple messages for the same day, log each separately.

---

## Step 2: Duplicate Check (Full-Day Entries)

```
aggregate(entity="events", where={"date": {"eq": "TARGET_DATE"}}, aggregate={"count": true})
```

If events exist: show them and ask "Adding more, or is this a duplicate?" — wait for response.

---

## Step 3: Context Gathering

Run in parallel before asking for narrative:

```
get_activities_by_date(start_date: "TARGET_DATE", end_date: "TARGET_DATE")
get_user_summary(date: "TARGET_DATE")
query(entity="events", where={"date": {"eq": "TARGET_DATE"}}, include=["location", "participants"], limit=50)
```

Also resolve current location and family context using `entity-resolution/locations.md` Generic Terms order. **Don't ask what you can look up.**

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

---

## Step 4: Extract Entities

From the narrative, list:
- People (including family terms — resolve contextually per `entity-resolution/people.md`)
- Locations (including generic: home/office/gym — resolve per `entity-resolution/locations.md`)
- Activities: workouts, meals, commutes, sleep, entertainment, secondhand events
- Biographical facts to capture (education, work, residence)

---

## Step 5: Entity Resolution Gate

Load and follow `entity-resolution/common.md` + the relevant type files. Do NOT skip.

Present summary and wait for confirmation before Step 6.

---

## Step 6: Create Events

**Order:** specialized tools first, then generic.

| Activity      | Tool                   | Key rule                                            |
|---------------|------------------------|-----------------------------------------------------|
| Workout       | `create_workout`       | Link Garmin for cardio; pre-audit ALL exercises      |
| Meal          | `create_meal`          | Must include `meal_items`; escalate if missing       |
| Commute       | `create_commute`       | Must have from_location_id + to_location_id          |
| Sleep         | `create_event` (sleep) | Spans midnight; check for existing first             |
| Entertainment | `create_entertainment` | Always include `event_type: "generic"` in event obj  |
| Work block    | `create_event` (work)  | Split around interruptions                           |
| Secondhand    | `create_event`         | Tag `["secondhand"]`, link to parent event           |
| Generic       | `create_event`         | Everything else                                      |

**Participants:** Include owner (Journal Person ID from `user-context.md`) on first-hand events.

**Locations:** Public venues require `place_id` from Google Places search. See `entity-resolution/locations.md`.

**Escalation codes** — return when required fields are missing (do not create incomplete records):
- `ESCALATE_MEAL_ITEMS` — no food items provided
- `ESCALATE_COMMUTE_ENDPOINTS` — missing from/to location
- `ESCALATE_WORKOUT_DETAIL` — no exercises and no Garmin link

### Garmin Linking (Mandatory for cardio: runs, bikes, swims, hikes, walks)

1. `get_activities_by_date(start_date, end_date)` — match by type + closest startTimeLocal
2. Link via `external_event_source: "garmin"`, `external_event_id: "<activityId>"`
3. Do NOT copy Garmin metrics into DB fields or notes
4. If multiple matches: ask one question to disambiguate

### Sleep Events

Span midnight. Two-step capture — log bedtime with null end_time, update when wake time is known. Always check for existing sleep event before creating.

---

## Step 7: Integrity Check (Full-Day Entries Only)

After creation, query and verify:
1. Workout/meal/commute events have specialization data (not just a generic event record)
2. First-hand events have owner as participant
3. Events with mentioned locations have `location_id` set

---

## Step 8: Confirm

"Logged [N] events for [DATE]: sleep, workout, 2 meals, commute."
