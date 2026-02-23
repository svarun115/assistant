# PLAN Mode

Collaborative scheduling. Loaded on demand (when user says "plan" mid-session, or during SETUP Step 6).

## When This Runs

- **SETUP:** After state presentation and unlogged gap questions, when user is ready to build the day
- **Mid-session:** User says "plan", "let's reschedule", "can we plan the rest of the day?"
- **Revision:** User wants to restructure the existing plan (increments `version`)

## Step 1: Know the Constraints

Before drafting, assemble:

1. **Available time windows** — current time to 9 PM (or user's stated end time), minus:
   - Already-logged events (from journal agent state or `daily-plan.md` timeline)
   - Fixed calendar blocks (from Google Calendar)
   - Fixed daily blocks from `user-prefs.md` (morning planning 10 AM, evening review 11 PM)

2. **Items to schedule** — from:
   - Google Tasks: overdue + today + this week (fetched during SETUP; task IDs retained in memory)
   - User-stated priorities in the current conversation
   - Tasks with `Deadline: YYYY-MM-DD` in notes — surface as must-do if deadline is today or tomorrow
   - Note: "deferred items from yesterday" = tasks that were rescheduled in Google Tasks to today during wrap-up. They appear in today's Google Tasks fetch automatically — do NOT pull from yesterday's `daily-plan.md`.

3. **Time budget** (from `user-prefs.md`):
   - Work: 6–8 hours
   - Personal: 2–3 hours (daily cap: 3 hours)
   - Health: 1–1.5 hours

## Step 2: Draft the Plan

Build a timeline that:
- Fills available windows with the prioritized task list
- Respects daily budget caps — warn if any category exceeds cap
- Groups related tasks (e.g., admin tasks together)
- Leaves buffer between items (don't schedule wall-to-wall)
- Schedules must-do-today items first, then this-week items

**Never double-book** — cross-check each slot against calendar events and already-logged events.

## Step 3: Present for Approval

Show a compact draft in chat:

```
## Draft Plan — [Date]

| Time | Activity | Category | Est. |
|------|----------|----------|------|
| 10:30–12:00 | Will Drafting | finance | 1.5h |
| 12:00–1:00 | Lunch | break | 1h |
| 2:00–3:30 | NSDL Account Setup | finance | 1.5h |
| 4:00–5:00 | Rental Search | personal | 1h |
| 6:00–7:00 | Walk | health | 1h |

**Time budget:** Work 0h · Personal 2.5h · Health 1h
**3 calendar conflicts checked — none**

Anything to change?
```

Wait for approval or revisions. Apply changes, re-present if structure changed significantly.

## Step 4: On Approval — Write `daily-plan.md`

Write the plan file at `~/.claude/data/daily-plan.md`:

```markdown
---
date: YYYY-MM-DD
version: 1          # increment if revising an existing plan
status: active
plan_id: ""         # populated in Phase 4
location: [from daily-context.json]
last_checkin: [current ISO 8601 timestamp with timezone]
---

# Daily Plan — [Full Date]

**BB at wake:** [N] → **Current:** [N] · **RHR:** [N] · **Sleep:** [Xh Ym]

## Timeline

| Time | Activity | Category | Status |
|------|----------|----------|--------|
| [wake time] | Wake | — | done |
| [already-logged items with done status] | ... | ... | done |
| [scheduled items] | ... | ... | planned |

## Today's TODOs
*(snapshot from Google Tasks — auto-populated during SETUP; this section is a view, not the source of truth)*
- [ ] [task title] ([list name])   ← overdue or due today
- [ ] [task title] ([list name]) ⚠️ deadline: [date]   ← if notes contain Deadline: today/tomorrow

## Notes
- [any active health conditions]
- [any notable context from today's state]
```

**Rules for Today's TODOs:**
- This section is written once during SETUP from Google Tasks data. Do NOT manually edit it between sessions.
- Completing a task: mark the checkbox `[x]` AND call `complete_task` in Google Tasks.
- Pushing a task to another day: update `due` in Google Tasks. Do NOT re-add it to the next day's plan manually — it will appear automatically in tomorrow's SETUP fetch.
- Never add a "Punted to Tomorrow" section — that concept does not exist. Use Google Tasks as the push-forward mechanism.

**Rules:**
- For revisions (mid-session plan changes): increment `version`, keep existing `done` statuses
- Respond in chat: "Plan saved — see `daily-plan.md`." Never reprint the timeline.

After writing the file, call `create_daily_plan` with the plan date, items, and time budget. Write the returned `plan_id` into the front matter of `daily-plan.md`. Store `item_ids` in memory — you'll need them for `update_plan_item` calls at check-in.

## Step 5: Create Calendar Events

After file is written, ask: "Should I add these to your calendar?"

If yes:
- Create events only for items that aren't already on the calendar
- Use category as `description` field context
- Confirm: "Added 3 events to your calendar."

If no: skip without asking again.

## Drift Detection

Track items that get rescheduled within the conversation. When an item has been pushed ≥ 2 times:
> "[Item] has been pushed twice. Still fitting it in today, or move to tomorrow?"

Apply at CHECK-IN too — read `version` history isn't available, but mid-session pushes are trackable.
