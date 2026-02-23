# Shared — Journal Integration & Error Handling

Cross-cutting rules loaded in every mode. Keep these in mind throughout all daily-tracker flows.

## Journal Agent: Spawn vs. Resume

`daily-context.json` tracks two kinds of agent sessions:

| Field | Purpose |
|-------|---------|
| `agent.journal_agent_id` + `agent.journal_agent_date` | Today's persistent agent (INIT/REFRESH/LOG) |
| `agent.pending_sessions["YYYY-MM-DD"]` | Past-date agents (e.g. yesterday's CONTEXT) that may be resumed for logging |

### Today's agent

Always check before spawning:

| Condition | Action |
|-----------|--------|
| `journal_agent_date` matches today + agent ID exists | **Resume** — pass `resume: <journal_agent_id>` |
| Date mismatch or missing | **Spawn** — new agent, save returned ID + today's date |

After spawning, write the new `journal_agent_id` and `journal_agent_date` (today) to `daily-context.json`.

### Past-date agents (`pending_sessions`)

When a past-date agent is spawned (e.g. CONTEXT for yesterday):
1. Save its agent ID to `agent.pending_sessions["YYYY-MM-DD"]` in `daily-context.json`
2. If the user later wants to log that date, **resume** the saved agent (it already has CONTEXT context loaded)
3. Once logging is complete, **remove** the entry from `pending_sessions`

If no entry exists for a date in `pending_sessions`, spawn a fresh agent for that date (CONTEXT first, then LOG).

`pending_sessions` should not accumulate stale entries — remove a session once its date's logging is confirmed done or explicitly skipped.

## Journal Agent: Always Background

All journal agent calls run with `run_in_background: true`. Launch background, then continue processing other parts of the request in parallel. Check output via `TaskOutput` before sending the response that depends on the result.

**Never ask the user who someone is or what a place is.** The journal knows — query it.

## Entity Resolution: Always-On

Whenever the user mentions a **person, location, or exercise** that is not already in the entity cache (`entity_cache.recent_people`, `entity_cache.recent_locations`, or `people_at_location`), immediately launch a QUERY in the background **in the same tool-call batch as any other actions**. Resolve in parallel — do not delay task creation, event logging, or other work while waiting.

```
mode: "QUERY"
entry_date: "<today>"
entities: [
  { raw: "<name as user said it>", type: "person|location|exercise", context: "<where/how mentioned>" }
]
include_context: true
context: { owner_id, location_id, entity_cache, people_at_location }
```

**Triggers:**
- User mentions a name not in `people_at_location` or `entity_cache.recent_people`
- User mentions a place not in `entity_cache.recent_locations`
- User asks anything about a specific person or place ("how's Priya?", "when did I last see Anmol?", "is Balance gym open?")
- User mentions an exercise in any workout-related context

**Pattern — use judgment:**
- **Context needed for the action** (e.g., person ID for logging, location for scheduling): fetch QUERY result before acting.
- **Context is conversational enrichment only** (e.g., last-seen date, relationship notes): launch QUERY background + execute the action in parallel. Surface context in the same response when results arrive.

**Use the context brief** in your response — reference last interactions, surface important person notes (health, career changes, achievements), mention who they typically go to a location with. Don't just acknowledge the entity; enrich the response with what you know.

**Cache write-back:** After QUERY returns, merge `new_entities` from the result into `entity_cache` in `daily-context.json`. This prevents repeat lookups within the session.

**Batch where possible:** If the user mentions multiple unknown entities in one message, resolve them all in a single QUERY call.

---

## Tool Scope

Direct calls: **Google Workspace only** (`mcp__google-workspace__*`). Everything else goes through the journal agent.

Google Workspace shares a single auth context (Calendar, Tasks, Gmail) — if one fails, all fail. Keep Google Workspace calls in their own parallel block.

## Error Handling

One attempt max for any failing call. Don't retry. Recovery depends on what failed:

### Google Workspace fails
Calendar and Tasks are unavailable — planning can't happen meaningfully without them. Tell the user clearly:
> "Google Workspace is unavailable — can't fetch your calendar or tasks. Planning is blocked until it's back."
Stop and wait. Don't attempt a degraded plan with missing data.

### Journal agent fails
Planning can still proceed — tasks and calendar are unaffected. Note it briefly:
> "Journal agent unavailable — activity logging and Garmin context are offline for now."
Proceed with planning using Google Workspace data. Log activities later when the agent is back.

### Tool/Query Failures
If a specific call fails (wrong format, unexpected response): don't retry with the same call. Pivot to an alternative approach or ask the user.

## Cross-System Follow-Through

After any write, consider: "What other system should reflect this?"

| Action | Follow-through |
|--------|---------------|
| Task created | Needs calendar block? |
| Task completed | Remove calendar event if one exists? Log to journal? |
| Calendar event created | Needs a task to track it? |
| Activity logged | `daily-plan.md` status updated? |
| Plan item marked done | (1) Google Tasks completion needed? (2) Check corresponding `- [ ]` checkbox in Today's TODOs section of `daily-plan.md` — mark it `- [x]` |

Ask or act — don't silently leave systems out of sync.

## `daily-context.json` Updates

When to write back to the cache:
- New journal agent spawned → write `journal_agent_id` + `journal_agent_date`
- Past-date agent spawned → write `agent.pending_sessions["YYYY-MM-DD"]`
- Past-date logging complete/skipped → remove `agent.pending_sessions["YYYY-MM-DD"]`
- Email triage run → write `last_email_triage`
- Location changes → write `location.current`

Minimize writes — only update fields that actually changed.
