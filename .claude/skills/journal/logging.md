# Journal Logging SOP

## Overview

This guide covers processing journal entries — from single-line quick logs to full-day narratives.

---

## CRITICAL: Log Every User Prompt (MANDATORY)

**Every user message containing journal content MUST be logged as a journal entry.**

This is non-negotiable. The user's input is the source of truth.

---

## Three-Tier Narrative Processing

Not all user messages should be logged the same way. Apply this tiered approach:

### Tier 1: FILTER — Remove Meta-Instructions

Before logging, identify and remove instructions/commands to the AI agent:
- Questions asking the AI to do something: "Can you log...", "Please update...", "Check if..."
- Directives: "Log the tennis activity", "Update the sleep timing", "Create an entry for..."
- Meta-commentary: "That looks wrong", "The timing seems off"
- Conversation management: "wait", "hold on", "nevermind", "continue"

**Only log the actual narrative content** — what happened, who was there, what you did, how you felt, what you observed.

### Tier 2: SYNTHESIZE — Q&A Into Narrative

When the user responds to assistant questions with short answers, synthesize the exchange into continuous first-person narrative:

**Example Q&A:**
```
Assistant: "What time did you leave the hotel?"
User: "9 AM"
Assistant: "How did you get to the consulate?"
User: "Took a Rapido cab"
```

**Synthesized narrative:**
```
"I left the hotel at 9 AM and took a Rapido cab to the consulate."
```

**Rules for synthesis:**
- Weave assistant questions into implicit context (don't include the questions themselves)
- Combine short answers into flowing first-person prose
- Preserve the user's exact phrasing for key details (names, times, places)
- Use past tense consistently
- Don't invent details — only rearrange what was stated

### Tier 3: PRESERVE — Rich Narratives Verbatim

When the user shares extended narratives (3+ sentences, story-like structure, emotional context), log them EXACTLY as written:

**Characteristics of rich narratives:**
- Multiple sentences with em-dashes or natural flow
- First-person storytelling voice
- Emotional context ("I was dejected", "caught me off guard")
- Sensory observations ("the cab driver spoke English", "tutti fruity naan")
- Reflections or self-critique ("I could have answered better")

**For these, log verbatim** (after filtering any meta-instructions from the same message).

---

### Decision Tree

For each user message:

1. **Does it contain meta-instructions?** → Filter them out (Tier 1)
2. **Is the remaining content:**
   - **Short answers to assistant questions?** → Synthesize into narrative (Tier 2)
   - **Extended narrative already in story form?** → Log verbatim (Tier 3)
3. **Mixed message (narrative + instructions)?** → Filter instructions, preserve/synthesize the narrative portion

---

### What to Log

After applying the three-tier approach, log:
- **ANY** user message describing events, activities, or experiences
- **ANY** user message providing biographical info about people
- **ANY** user message describing org structures, relationships, plans
- **ANY** user message with details that might be useful later
- Even partial/incomplete information — log it

### How to Log

```
log_journal_entry(
  entry_date: "YYYY-MM-DD",
  raw_text: "[PROCESSED USER NARRATIVE - filtered, synthesized, or preserved per three-tier approach]",
  entry_type: "journal",
  tags: ["user-input", ...]
)
```

### When to Log

- **IMMEDIATELY** after receiving user input, BEFORE processing events
- Log first, then create structured events from the logged content
- If user provides multiple messages for the same day, log EACH ONE separately

### What NOT to Do

- Do NOT summarize user input — log verbatim
- Do NOT skip logging because "it's just org structure info"
- Do NOT wait until end of processing to log
- Do NOT create your own summary instead of logging user's words
- Do NOT include instructions/directives to the AI — filter these out and log ONLY the narrative content

### Why This Matters

- User's exact words capture nuance, context, and details
- AI summaries lose information and introduce errors
- Raw logs enable future retrieval and correction
- The journal is the user's memory, not the AI's interpretation

---

## Entry Types

| Type | Example | Processing |
|------|---------|------------|
| **Single line** | "Had coffee with Mohit at 3pm" | Quick: resolve entities, create event, done |
| **Partial day** | A few paragraphs covering morning | Multiple events, entity resolution gate |
| **Full day** | Complete journal file | Full SOP with validation and integrity checks |
| **Backfill** | Past date entry | Context gathering first, then full SOP |
| **Block entry** | Multi-day (wedding, trip) | Process as connected events across days |

---

## Pre-Ingestion Validation (MANDATORY for full entries)

Before processing any full journal entry:

### Step 1: Parse Target Date

Extract from user message or file name. If ambiguous, ask.

### Step 2: Check Existing Events

Use `aggregate` to check if the date already has events:
```
aggregate(entity="events", where={"date": {"eq": "TARGET_DATE"}}, aggregate={"count": true})
```

### Step 3: If Events Exist

Query them to show the user:
```
query(entity="events", where={"date": {"eq": "TARGET_DATE"}}, orderBy="start", orderDir="asc", limit=10)
```

Present: "Jan 15 already has 8 events logged (sleep, workout, 3 meals, 2 commutes, work). Are you adding more, or is this a duplicate?"

**Wait for response before proceeding.**

### Step 4: If No Events

Proceed with context gathering.

---

## Context Gathering

### Location & Family Context (MANDATORY — Run First)

**Before anything else**, determine where the user is and who is with them.

#### Step 1: Check Spouse/Partner Location (MANDATORY)

Query the spouse/partner's current residence — don't assume:
```
query(entity="people", where={"relationship": {"eq": "partner"}}, include=["relationships"])
```
Then check their residence records.

#### Step 2: Check Recent Events for Physical Presence

Query recent events with participants and location:
```
query(entity="events", where={"date": {"gte": "TARGET_DATE-3"}, "category": {"in": ["family", "social", "travel"]}}, include=["participants", "location"], limit=10)
```

#### Step 3: Search Journal for Travel Context

```
search_journal_history(query="where am I, who is with me, travel, family, parents, visiting", start_date="TARGET_DATE-7", limit=5)
```

#### Step 4: Apply Inference Rules

**Phone/Video Call Rule:** If recent entries show phone or video calls with someone, they are **NOT physically co-located**. This is definitive — don't ask for confirmation.

**Co-location Indicators:**
- In-person meals together → physically present
- Phone/video calls → remote/different location
- "Spoke to X" without location context → likely remote
- "With X" or "X and I went..." → physically present

#### Step 5: Don't Ask What You Can Look Up

**CRITICAL:** Before asking the user a question, check if the answer exists in the database:
- Spouse location? → Check person residences
- Where was user last week? → Check recent events with locations
- Who is X related to? → Check person relationships

Only ask the user when the DB genuinely doesn't have the answer.

**Present context summary:**
```
**Current Context:**
- Location: Manyata Residency, Bangalore
- With: Amma, Acha, Amooma, Apoopa
- Gauri: In New York (confirmed via residence record + phone calls in recent entries)
```

### For Same-Day Entries

Fetch before asking for narrative:
1. **Location & family context** — (see above, MANDATORY)
2. **Garmin activities** — `get_activities_by_date`
3. **Garmin health** — `get_user_summary` (sleep, wake, Body Battery, stress)
4. **Email context** — `search_emails` (deliveries, travel receipts, credit card transactions)
5. **Existing events** — What's already logged?

### For Backfills (Past Dates) — MANDATORY

**Before asking for details**, gather context by running these in parallel:

```
query(entity="events", where={date: {eq: "<TARGET_DATE>"}},
  include=["workout", "meal", "commute", "entertainment", "location"],
  orderBy="start", orderDir="asc", limit=200)

query(entity="journal_entries", where={date: {eq: "<TARGET_DATE>"}}, limit=50)

get_user_summary(date: "<TARGET_DATE>")
get_activities_by_date(start_date: "<TARGET_DATE>", end_date: "<TARGET_DATE>")
```

Then build the timeline skeleton (see **Present Timeline Skeleton** below) and present it to the user. Ask them to fill the gaps, then proceed to logging.

---

## Present Timeline Skeleton (MANDATORY)

**Always present a timeline skeleton** after gathering context to help the user fill gaps.

### Timeline Sources

Build the skeleton from:
1. **Garmin sleep** — bedtime (previous night) and wake time
2. **Garmin activities** — workouts with exact timestamps
3. **Existing events** — if any already logged
4. **Nearby days** — for travel/location continuity

### Format

```
**Timeline Skeleton for [DATE]:**

| Time | Source | Event |
|------|--------|-------|
| ~HH:MM | Garmin | Bedtime (night of [DATE-1]) |
| ~HH:MM | Garmin | Wake (Body Battery X, ~N hrs sleep) |
| HH:MM–HH:MM | **?** | Morning — **please fill** |
| HH:MM–HH:MM | Garmin | [Activity: distance, type] |
| HH:MM–HH:MM | **?** | Afternoon/Evening — **please fill** |
| HH:MM–sleep | **?** | Night — **please fill** |

**Questions:**
1. [Specific questions about gaps]
```

### Guidelines

- Mark known events with their source (Garmin, DB, Email)
- Mark gaps with `**?**` and `**please fill**`
- Include Body Battery at wake for energy context
- For multi-day gaps, present one day at a time
- Don't overwhelm — 3 questions max

---

## Processing Narrative

### Step 1: Read Exactly

**CRITICAL:** Read the raw text EXACTLY as written.

Common failure: Hallucinating similar words ("Voice journalling" → "Watched Journey")

**Fix:** After extracting entities, re-read the relevant sentence and confirm interpretation.

### Step 2: Extract Entities

From the narrative, list:
- **People** (including family terms)
- **Locations** (including generic: home/office/gym)
- **Activities** to structure: workouts, meals, commutes, sleep, entertainment, work blocks
- **Secondhand events**: Things that happened to others that you learned about

### Step 3: Entity Resolution Gate

See `entities.md` for full procedure. Do NOT skip this.

### Step 4: Date/Time Anchoring

- Infer entry_date from context (sleep boundaries, relative phrasing)
- If not confidently inferable, ask ONE question
- Don't invent timestamps — if "this morning" has no anchor, leave time unspecified
- **Midnight spillover:** Treat 00:00–02:00 events as possible same-day if user hasn't slept

### Step 5: Present Extraction Plan (MANDATORY)

**Before creating ANY events**, present the full extraction plan to user and wait for confirmation.

**Format:**
```
## Extraction Plan for [DATE]

### People Identified
- [Name] — [existing/new] — [relationship context if new]

### Locations Identified
- [Location] — [existing/new]

### Events to Create ([count])
1. [Time] — [Event type] — [Title] — [Participants]
2. ...

### Garmin Links
- [Activity] → Garmin ID [xxx]

### Questions (if any)
- [Clarifications needed]

---
**Proceed with logging?**
```

**WAIT for explicit user confirmation before proceeding to Step 6.**

### Step 6: Create Structured Events

**Order:** Specialized first, then generic.

| Activity | Tool | Notes |
|----------|------|-------|
| Workout | `create_workout` | Link Garmin if cardio |
| Meal | `create_meal` | Include meal_items |
| Commute | `create_commute` | MUST have from/to locations |
| Sleep | `create_event` (type: sleep) | Spans midnight, may be two-step |
| Entertainment | `create_entertainment` | Movies, shows, gaming, reading |
| Work block | `create_event` (type: work) | Split around interruptions |
| Secondhand | `create_event` | Events learned about, not witnessed |
| Generic | `create_event` | Everything else |

**Participants:** Include the owner on first-hand events (see `~/.claude/data/user-context.md` for owner identity and Journal Person ID).

**Locations:** See enforcement rules below.

### Required Fields & Escalation

Certain event types have **required fields** that must be present. If missing and the caller hasn't explicitly said to skip, **escalate** instead of creating an incomplete record.

| Event Type | Required Field | Escalation Code | Notes |
|-----------|---------------|-----------------|-------|
| Meal (`create_meal`) | `meal_items` (food items list) | `ESCALATE_MEAL_ITEMS` | Don't create a meal with empty items. Escalate so the calling skill can prompt the user. |
| Commute (`create_commute`) | `from_location_id`, `to_location_id` | `ESCALATE_COMMUTE_ENDPOINTS` | See Location Enforcement below. |
| Workout (`create_workout`) | At least one exercise OR Garmin link | `ESCALATE_WORKOUT_DETAIL` | A workout with no exercises and no Garmin link has no useful data. |

**How to escalate:** Return the escalation code in the batch result. The calling skill decides whether to prompt the user or skip. The agent does NOT create the record until the missing data is provided or the caller explicitly says to skip.

**Caller override:** If the caller's instruction includes "skip items" or "no detail needed", create the record without the required field. The escalation only applies when data is missing with no explicit skip.

### Step 7: Log Raw Journal Entry

```
log_journal_entry(entry_date: "YYYY-MM-DD", raw_text: "[verbatim user narrative]")
```

**One entry per user message.** May combine if user explicitly requests.

---

## Location Enforcement (MANDATORY)

### Non-Commute Events

SHOULD have `location_id` when a place is mentioned.

- **Public venue:** Resolve via Google Places, get `place_id`
- **Private place:** Create without `place_id`
- **Unknown/unstated:** Note in `event.notes`: "Location not specified"

### Commute Events

MUST have both `from_location_id` AND `to_location_id`.

Never create a commute with missing endpoints. Use home inference (see `entities.md`) before asking.

---

## Sleep Event Handling

Sleep events span midnight: bedtime Day N → wake time Day N+1.

### Two-Step Capture

1. **User provides sleep time:** Create sleep event with `start_time`, leave `end_time` null
2. **User later provides wake time:** Update existing sleep event to fill `end_time`

Don't force user to provide both at once.

### Check for Existing Sleep

Query for existing sleep events on the date before creating:
```
query(entity="events", where={"type": {"eq": "sleep"}, "date": {"in": ["YYYY-MM-DD", "YYYY-MM-DD+1"]}})
```

If exists, update rather than create duplicate.

### Sleep Segmentation

If user reports waking and returning to sleep:
- End first sleep at first wake
- Create second sleep for return-to-sleep
- "Awake in bed" (cuddling, reading) = separate generic event, not sleep

---

## Garmin Linking (MANDATORY for cardio)

For run/bike/walk/hike/swim when date is known:

### Step 1: Query Garmin

```
get_activities_by_date(start_date: "YYYY-MM-DD", end_date: "YYYY-MM-DD")
```

### Step 2: Match Activity

- Filter by activity_type
- Match by closest `startTimeLocal` to journal event (allow warm-up buffer)
- Cross-check with distance/duration hints

### Step 3: Link

If exactly one match:
```
external_event_source: "garmin"
external_event_id: "<activityId>"
```

**Do NOT copy** Garmin metrics into DB fields/notes.

### Step 4: If Multiple/None

Ask ONE question: "I see two runs this morning (6.1km at 7am, 8.0km at 8:30am). Which one?"

---

## Entertainment Classification

Any media consumption MUST be entertainment, not generic event.

| Activity | Type |
|----------|------|
| Watched movie | `movie` |
| Watched TV show | `tv_show` |
| Watched sports/YouTube | `streaming` |
| Played video game | `gaming` |
| Read book/article | `reading` |
| Listened to podcast | `podcast` |
| Concert/theater | `live_performance` |

**completion_status:** Whether media was finished (started/in_progress/finished/abandoned), independent of event `end_time`.

---

## Post-Ingestion Integrity Check

Run after processing full-day narratives:

### 1. Specialization Coverage

Query all events for the date with specialization includes:
```
query(entity="events", where={"date": {"eq": "TARGET_DATE"}}, include=["workout", "meal", "commute", "entertainment"], orderBy="start", orderDir="asc")
```

Red flag: Event typed as workout/meal but no specialization data in the include.

### 2. Participant Integrity

Query events with participants:
```
query(entity="events", where={"date": {"eq": "TARGET_DATE"}, "type": {"in": ["meal", "workout", "commute"]}}, include=["participants"])
```

Red flag: First-hand meal/workout/commute without owner as participant.

### 3. Location Completeness

Query events missing location:
```
query(entity="events", where={"date": {"eq": "TARGET_DATE"}, "location_id": {"isNull": true}, "type": {"neq": "commute"}})
```

---

## Secondhand Events

Events the user learned about but didn't witness.

### When to Create

- Significant life events (accidents, achievements)
- Events affecting family/close relationships
- Incidents prompting action (safety improvements)

### Structure

```json
{
  "title": "Amooma's Bathroom Slip (Secondhand)",
  "event_type": "generic",
  "participant_ids": ["amooma-uuid"],
  "parent_event_id": "phone-call-uuid",
  "source_person_id": "person-who-told-you",
  "tags": ["secondhand"],
  "notes": "Learned from Amma during Sep 30 call"
}
```

**Timestamps:** Required but don't invent. If unknown, store in raw journal entry and wait.
