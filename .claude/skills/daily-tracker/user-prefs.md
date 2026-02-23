# Daily Tracker — User Preferences

## Time Boundaries

| Type | Default |
|------|---------|
| **Work Hours** | 10:00 AM - 6:00 PM |
| **Personal Tasks Window** | Outside work hours + breaks |
| **Daily Personal Cap** | 3 hours max |

## Fixed Daily Blocks

| Time | Duration | Purpose |
|------|----------|---------|
| 10:00 AM | 30 min | Morning planning |
| 11:00 PM | 30 min | Evening review |

## Priority Rules

1. **Tasks with deadlines** — Schedule before deadline date
2. **Urgent tasks** — Same day or next available slot
3. **Regular tasks** — Fit within available windows

## Google Tasks = Personal Tasks

All items in Google Tasks are personal tasks. They must **never** be scheduled during work hours (10 AM – 6 PM). Only schedule them in personal windows: mornings before 10 AM, evenings after 6 PM, or on non-working days. Exception: explicitly work-related task lists (if any are added in future).

## Time Budget Categories

| Category | Daily Target | Examples |
|----------|-------------|----------|
| Work | 6-8 hours | Meetings, focused work, email |
| Personal | 2-3 hours | Errands, reading, hobbies |
| Health | 1-1.5 hours | Workout, walk, stretching |
| Break | Built-in | Meals, rest, transition time |

## Task Persistence Model

| Concept | Storage | Meaning |
|---------|---------|---------|
| **Scheduled date** | Google Tasks `due` field | When you plan to work on it |
| **Deadline** | Task notes: `Deadline: YYYY-MM-DD` | When it must be done — only add if different from scheduled date |
| **Source of truth** | Google Tasks | All task state lives here |
| **Daily snapshot** | `daily-plan.md` Today's TODOs | Read-only view, populated during SETUP |

**Terminology:** Always use "scheduled" when referring to when a task is planned. Use "deadline" for the hard cutoff. The Google Tasks `due` field stores the scheduled date — its UI label says "due date" but we treat it as the scheduled date.

**Rules:**
- All task persistence across days flows through Google Tasks — never through `daily-plan.md`
- `daily-plan.md` Today's TODOs = read-only snapshot, populated during SETUP from Google Tasks
- Checkboxes in Today's TODOs are a visual convenience for the day only — Google Tasks is authoritative
- When pushing tasks forward (WRAP-UP), update the Google Tasks `due` field (scheduled date) — do NOT re-add tasks to `daily-plan.md` manually
- A task with `Deadline: YYYY-MM-DD` in its notes must be surfaced as urgent on that date, even if the scheduled date is different
- Never modify a `Deadline:` note when rescheduling — only update the `due` field (scheduled date)
