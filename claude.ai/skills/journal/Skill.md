# Journal — Log & Query

**Description:** The user's personal memory system. Use this skill in three situations:
1. **Any time a person, place, or journaled entity is mentioned** (family, friend, colleague, restaurant, gym, past event, past meal, commute) — silently look it up to fetch context. Do this proactively and without announcing it, even when the user isn't explicitly asking.
2. **When the user describes something that happened** — log it as a structured journal event (meals, workouts, commutes, travel, social events, reflections, anything).
3. **When the user asks about their own life, history, or people** — search the journal to answer ("when did I last...", "how often do I...", "who is X", "what did I do on...").

**MCPs:** personal-journal, google-places, garmin

---

## On-Demand File Loading

Load files as needed — do not load everything upfront.

| When | Load |
|------|------|
| Entering LOG mode | `modes/log.md` |
| Entering REFLECT mode | `modes/reflect.md` |
| Entering QUERY mode | `modes/query.md` |
| Resolving any entity | `entity-resolution/common.md` |
| Resolving a person | + `entity-resolution/people.md` |
| Resolving a location | + `entity-resolution/locations.md` |
| Resolving an exercise | + `entity-resolution/exercises.md` |
| Need enum values (meal types, workout subtypes, etc.) | `journal-data-model.md` |

**Project knowledge always in context:** `user-context.md` (identity + family IDs with Journal UUIDs)

---

## Intent Detection

| Signal | Mode |
|--------|------|
| Any person, place, or journaled entity mentioned → silently look it up | context fetch (run first, no output) |
| Past-tense reports, "Had X then Y", "Here's my day..." | LOG |
| Emotional language, ruminating, "I've been thinking about..." | REFLECT |
| Questions, "when did I...", "how many...", corrections | QUERY |

**Context fetching is not a mode — it's a silent reflex.** Whenever any entity is mentioned (person, location, or past event type like "the usual lunch spot"), resolve it from the journal before doing anything else. Don't announce it, don't show tool calls — just have the context ready to inform the response.

**Mode persistence:** Stay in detected mode. Switch only when shift signal is clear.

**Explicit overrides:** "log this" → LOG, "just reflecting" → REFLECT

---

## The Two Shelves (Always Available)

The journal has two parallel ways to search — use the right one for the question:

| Shelf | Tool | Best For |
|-------|------|----------|
| **Structured** | `query` / `aggregate` | Counts, dates, participants, timelines, precise facts |
| **Semantic** | `semantic_search` | Feelings, themes, fuzzy recall, stories, ambiguous names |

**Applies in all modes and contexts:**
- Entity resolution: if `query` finds nothing by name, try `semantic_search` before concluding the entity doesn't exist
- LOG mode backfill: use `semantic_search` to find journal context for a date before asking the user
- REFLECT mode: search for past patterns by emotion or theme
- QUERY mode: cross-verify important facts on both shelves
- Garmin is the source of truth for workout stats — query it directly, not the journal

---

## Non-Negotiables (All Modes)

1. **Never invent details** — if unknown, ask (max 1 question in REFLECT, max 3 in LOG)
2. **Search before create** — always search existing entities before creating new ones
3. **Stop on errors** — if any tool fails, stop and report to user
4. **Never show UUIDs** — present as "[Name] (your partner)"
5. **Facts vs inferences** — label clearly in LOG and QUERY modes
