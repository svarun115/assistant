# CHECK-IN Mode

Lightweight midday invocation. Reads the existing plan, checks progress, updates `daily-plan.md`. No full task reload or email scan.

## Step 0: Check System Time (MANDATORY)

Run `date` via Bash **before every check-in response**. Never assume the time from context or conversation flow — the session may have been idle for hours.

> **CRITICAL:** Steps 1c (journal REFRESH) and 1d (Garmin) MUST be launched immediately after checking time — before asking the user any questions. Never ask "what happened since X?" before receiving the journal state bundle. The journal tells you what happened; the user fills in gaps the journal doesn't cover.

## Step 1: Read Plan + Fetch Updates in Parallel

**1a. Read `~/.claude/data/daily-plan.md`** — get timeline, `plan_id` from front matter

**1b. Read `~/.claude/data/daily-context.json`** — get `entity_cache`, `people_at_location`, `agent.*`, `garmin.wake_time`

**1c. Resume journal agent (REFRESH mode, background):**
```
mode: "REFRESH"
entry_date: "<today>"
context:
  owner_id: "<from daily-context.json owner.id>"
  location_id: "<from daily-context.json location.id>"
  people_at_location: <from daily-context.json people_at_location>
  entity_cache: <from daily-context.json entity_cache>
```
REFRESH runs: today's **events** (Query 1) + today's **journal_entries** (Query 2) + Garmin BB update. Both entities must be queried — /done and /journal skills log to `journal_entries`, not `events`. Omitting journal_entries causes false gap reports. Entity cache comes from context — no DB queries for entity resolution.

**1d. Garmin:** `get_user_summary(date: "<today>")` — current Body Battery only

Run 1c + 1d in parallel. 1a + 1b are local file reads.

## Step 2: Compare Plan vs. Logged

From the plan's Timeline table:
1. Identify planned items that should have happened
2. Check which are covered by logged journal events (title + time overlap)
3. Flag: **completed** (journal event found), **overdue** (past, not logged), **upcoming** (still ahead)

Calculate remaining time vs. what's left in the plan.

## Step 3: Ask About Gaps

Ask contextually — reference specific planned items:
- "You had [item] planned for [time]. How did that go?"
- If multiple: "Walk me through what happened since [time]."
- If nothing planned: "What have you been up to since [time]?"

## Step 4: Log Reported Activities

If the user describes past activities: delegate to journal agent (LOG mode, background). Acknowledge immediately. Check output before next response.

After journal agent returns: write any `new_entities` from the bundle back to `entity_cache` in `daily-context.json`.

## Step 5: Update `daily-plan.md`

Edit the file in place:
- Update status fields in Timeline: `planned` → `done` / `skipped` / `in-progress`
- Add unplanned events to the Timeline table
- Update the `*Updated HH:MM*` timestamp in the header

For each item whose status changed, call `update_plan_item(item_id, status, actual_event_id?)`. Item IDs are in the `plan_id`-linked `planned_items` DB records — query via `execute_sql_query` if not in memory: `SELECT id, title FROM planned_items WHERE plan_id = '<plan_id>'`.

## Step 6: Respond in Chat

Brief acknowledgment only. Examples:
- "Got it — Will Drafting done. Rental Search still ahead. Daily plan updated."
- "Logged the lunch. Plan updated."

**Never reprint the full timeline.** User can check `daily-plan.md` for the full picture.

## On-Demand Gap Review

If the user asks to review or complete a previous day's journal, invoke journal agent in CONTEXT mode for that date, present the timeline skeleton, and offer to fill gaps via LOG. Otherwise do not trigger CONTEXT at check-in — that runs at SETUP (yesterday) and wrap-up (today).

## Schedule Drift Detection

Track rescheduled items within the conversation. When an item has been pushed ≥ 2 times:
> "Rental Search has been pushed twice. Still fitting it in today, or move to tomorrow?"
