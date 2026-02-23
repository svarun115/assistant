# Logging — Activity Reporting

Loaded when the user reports a past activity mid-session. Governs how to delegate to the journal agent.

## When This Runs

User reports something that happened: "I just got back from lunch", "Had a call with X", "Went for a walk earlier", "Finished the Will Drafting". Any past-tense activity report triggers this flow.

**Acknowledge immediately.** Don't wait for journal agent to finish. Say "Got it, logging that." Then run the agent in background.

## Delegation Principle

**All journal writes go through the journal agent.** Resume today's agent in LOG mode:

```
mode: "LOG"
entry_date: "<today>"
context:
  owner_id: "<from daily-context.json>"
  location_id: "<from daily-context.json>"
  people_at_location: <from daily-context.json>
  entity_cache: <from daily-context.json>
events: [
  {
    entry_text: "<user's description, lightly cleaned>",
    event_type_hint: "<meal|workout|work|social|errand|...>",   // optional
    time_range: { start: "<HH:MM>", end: "<HH:MM>" },           // if mentioned
    participants_mentioned: ["<names>"]                          // if mentioned
  }
]
```

Run with `run_in_background: true`. Check output before the next response that would reference the logged data.

## Three-Tier Pass-Through

The journal agent applies this filtering — you don't need to second-guess it. But know what it does:

1. **Filter** — Decide if something is worth logging (skip throwaway mentions like "I checked my phone")
2. **Synthesize** — Convert casual descriptions into structured events (meal → {location, items, participants})
3. **Preserve** — Keep the user's own words in the `notes` field; don't over-sanitize

Your job is to pass the user's description through faithfully. Don't pre-process or rewrite it heavily.

## What Triggers a Log

Log when the user describes:
- A meal (any: breakfast, lunch, dinner, snack, coffee)
- A workout or physical activity (walk, run, gym, stretching)
- A work session (meeting, focused work, call, review)
- A social interaction (call with family, meeting a friend)
- An errand or task completion (finished X, went to Y)
- Travel / commuting
- Entertainment (watched, read, listened to)
- Health events (took medicine, symptom change)

Don't log: vague meta-comments, future intentions, quick conversational filler.

## Completeness Checks

### Meals
If the user mentions eating but doesn't say where or what: ask once.
- "What did you have / where was it?" (combine into one question)
- If they don't know / don't remember: log what you have, move on.

### Workouts
If the user mentions a workout, check Garmin for a matching activity (`get_activities_by_date`) — this gives duration, HR, and calories automatically. The journal agent handles this internally on workout-type events.

### People
If the user says "had lunch with X" and X isn't in `recent_people`, note it in `participants_mentioned`. The journal agent will resolve or create the person.

## Plan Status Update

After logging a completed activity, also update `daily-plan.md` if:
- The activity matches a planned item → change status to `done`
- The activity was unplanned → add a row to the Timeline table

Update the file in place. Brief chat acknowledgment: "Logged + plan updated."

## Escalation

If the user reports something that requires journal data you don't have (e.g., "add a note to the person I met last week" — needs person ID), ask the journal agent in QUERY mode first, then log.
