# WRAP-UP Mode

End-of-day retrospective. Compares plan vs. actual, logs gaps, pushes unfinished items forward, archives the plan.

## Step 1: Read Plan + Launch CONTEXT in Parallel

**1a. Read `~/.claude/data/daily-plan.md`** — get full timeline, `plan_id` from front matter

**1b. Read `~/.claude/data/daily-context.json`** — get `entity_cache`, `people_at_location`, `agent.*`

**1c. Resume today's journal agent in CONTEXT mode (background):**

Use `resume: <journal_agent_id>` from `daily-context.json` — today's agent is already alive from SETUP with skill files loaded. No fresh spawn needed.
```
mode: "CONTEXT"
entry_date: "<today>"
gap_threshold_minutes: 30
resume: "<agent.journal_agent_id>"
context:
  owner_id: "<from daily-context.json owner.id>"
  location_id: "<from daily-context.json location.id>"
  people_at_location: <from daily-context.json people_at_location>
  entity_cache: <from daily-context.json entity_cache>
```
CONTEXT fetches everything needed for wrap-up in one call: today's events (full includes), journal entries, Garmin summary + activities, and pre-built gap detection. No separate REFRESH or Garmin call needed.

1a + 1b are local file reads. 1c runs in background concurrently.

## Step 2: Build Plan vs. Actual

Wait for the CONTEXT result (1c). Using it + the plan's Timeline:

1. Match logged events to planned items (title similarity + time overlap)
2. Classify each planned item: **done**, **partial**, **skipped**, **moved** (rescheduled)
3. Identify **unplanned events** (logged events with no matching planned item)
4. Calculate:
   - Completion rate: completed / total planned
   - Unlogged gaps: from CONTEXT `GAPS` section

## Step 3: Present Summary + Ask About Gaps

Show a compact plan-vs-actual summary in chat:

```
## Wrap-Up — [Date]

**Completed:** [N]/[M] items · **Unlogged gaps:** [N]
**Garmin:** [steps] steps · BB end: [N]

| Time | Planned | Status | Actual |
|------|---------|--------|--------|
| ... | ... | done/skipped/moved | ... |
| [gap] | — | unlogged | — |
```

Then ask contextually about unlogged gaps:
- Reference what was scheduled during the gap
- If nothing scheduled: "What happened between [time] and [time]?"

Wait for user input. Log anything reported via journal agent (LOG, background). Acknowledge immediately.

After journal agent returns: write any `new_entities` back to `entity_cache` in `daily-context.json`.

## Step 4: Push Unfinished Items Forward

For each item still `planned` or `in-progress`:

1. **Ask once:** "Rental Search wasn't completed — move to tomorrow, or drop it?"
   - Batch multiple items: "Three items weren't done — walk me through what to do with each?"
2. On "tomorrow": `update_task(tasklist_id, task_id, due: "<tomorrow>")` — update the scheduled (`due`) date only
3. On "drop it": `complete_task` or delete — note in `day_summary`
4. On "move to [specific date]": `update_task` with that date

**Critical rules:**
- Update Google Tasks `due` (scheduled date) only. **Never modify `Deadline:` in task notes** — that stays fixed.
- Do NOT re-add unfinished tasks to tomorrow's `daily-plan.md` manually. Google Tasks is authoritative; the task will surface automatically in tomorrow's SETUP fetch.
- Don't ask about already-skipped or explicitly-moved items.

## Step 5: Create Day Summary Journal Entry

Log one `journal_entries` entry via journal agent (LOG mode):

```
type: "day_summary"
entry_date: "<today>"
content: Compact narrative:
  - Items completed, skipped, and why
  - Key unplanned events
  - One-sentence overall assessment
```

After logging, call `get_plan_vs_actual(plan_date: "<today>")` using the `plan_id` from `daily-plan.md` front matter. Use `summary.completion_rate_pct` in the chat closing message if informative.

## Step 6: Preview Tomorrow (Optional)

If the user asks or it's a natural moment:
- Check Google Calendar for tomorrow's events
- Fetch Google Tasks with `due: "<tomorrow>"` — these are items scheduled for tomorrow (including any just pushed forward in Step 4). Also scan notes for `Deadline: <tomorrow>` across all open tasks.
- Note any time conflicts or urgent deadlines

Don't build a full plan unless the user explicitly asks. Tomorrow's SETUP will handle it.

## Step 7: Archive + Mark Complete

1. Update the `*Updated HH:MM*` timestamp in `daily-plan.md` header
2. Copy file to `~/.claude/data/plans/archive/YYYY-MM-DD.md`
3. Leave `daily-plan.md` in place — it still shows today's summary

## Step 8: Respond in Chat

Brief closing. Examples:
- "Wrap-up done — 4/6 items completed. Rental Search moved to tomorrow. Plan archived."
- "All done. Day summary logged. Nothing carried forward."

**Never reprint the full plan or day summary in chat.** The file is the record.
