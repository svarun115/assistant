# Task Mode

Loaded when the user wants to create, complete, or manage a task. Returns to the calling mode after.

## When This Runs

- User says "add a task", "remind me to", "create a todo", "I need to [do X]"
- User marks a task complete outside of the normal check-in flow
- User wants to move/reschedule a task

## Creating a Task

### Step 1: Gather Minimum Required Info

You need: **title** and **list**. Everything else is optional.

If not clear from context, ask in one message:
- "What list should this go in?" (show available lists if helpful)
- "When are you scheduling it? And is there a separate deadline?"

Don't ask separately. Combine into one question. If the user's message already has enough, don't ask at all.

**Scheduled vs Deadline model:**
- `due` field = **scheduled date** (when you plan to work on it)
- `notes` field = add `Deadline: YYYY-MM-DD` prefix if there's a hard deadline that differs from the scheduled date
- If scheduled date = deadline: just use `due`. No notes prefix needed.

### Step 2: Create in Google Tasks

```
create_task(
  tasklist_id: "<id>",
  title: "<title>",
  due: "<YYYY-MM-DD>",              // scheduled date
  notes: "Deadline: YYYY-MM-DD\n<any other notes>"  // only if deadline ≠ scheduled date
)
```

### Step 3: Cross-System Check

After creating, ask once: "Does this need a calendar block?"

- Yes → load plan-mode.md logic, find a slot, create calendar event, link in task notes
- No / not now → skip

If the task is time-sensitive and there's a clear slot available, suggest it proactively rather than just asking.

### Step 4: Log to `daily-plan.md` (if scheduled today)

If the task is scheduled for today or the user says "I'll do this today", add it to the Today's TODOs section of `daily-plan.md`:
```
- [ ] [title] ([list name])
```

## Completing a Task

When a user says they finished a task that's in Google Tasks:

1. Mark complete: `complete_task(tasklist_id, task_id)`
2. If it was in `daily-plan.md`: update status to `done` in the Timeline or TODO list
3. If it was a significant work item: it will be logged via the normal activity logging flow — don't double-log here

## Moving / Rescheduling a Task

Update the scheduled date only: `update_task(tasklist_id, task_id, due: "<new date>")`

**Never modify the `Deadline:` prefix in notes when rescheduling** — the hard deadline stays fixed regardless of when you reschedule the work.

If it was in today's `daily-plan.md` Today's TODOs: update status to `moved`, add note. The task will reappear automatically in tomorrow's SETUP fetch.

## Response

Brief confirmation after any task action:
- "Added to [List]. No calendar block."
- "Added to [List] — blocked 2–3 PM on your calendar."
- "[Task] marked complete."

Don't elaborate unless asked.
