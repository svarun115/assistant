# Journal Agent — CONTEXT Mode

Produces a timeline skeleton for a specific date showing what's logged, what's unlogged, and where the gaps are. Read-only — no logging or entity creation.

**Load on entry if not already in context from INIT** (e.g. when spawned fresh as a past-date agent):
- `~/.claude/skills/journal/gotchas.md` — query field names, enum values, query discipline rules

---

## Step 1: Fetch in Parallel

```
query(entity="events", where={date: {eq: "<entry_date>"}},
  include=["workout", "meal", "commute", "entertainment", "location"],
  orderBy="start", orderDir="asc", limit=200)

query(entity="journal_entries", where={date: {eq: "<entry_date>"}}, limit=50)

get_user_summary(date: "<entry_date>")
get_activities_by_date(start_date: "<entry_date>", end_date: "<entry_date>")
```

---

## Step 2: Build Timeline

1. **Sort DB events** by start time ascending
2. **Extract Garmin sleep block** from `bodyBatteryActivityEventList` where `eventType == "SLEEP"` — convert GMT to IST (offset: +05:30). Note BB at wake.
3. **Extract Garmin activities** from `get_activities_by_date` — for each: `activityName`, `startTimeLocal`, `duration` (seconds), `activityId`
4. **Match Garmin activities to DB events**: match if DB event start is within ±15 min of Garmin `startTimeLocal` AND event type is workout. Mark matched; flag unmatched.
5. **Detect gaps**: For each consecutive pair of DB events, if `next.start − prev.end > gap_threshold_minutes` → flag as a gap row. Also check before first event (after inferred wake) and after last event (before midnight or inferred sleep).
6. **Build timeline table**: one row per DB event + one row per gap.

Default `gap_threshold_minutes`: 60 (use value from input if provided).

---

## Step 3: Return GAP_REVIEW_RESULT

```
GAP_REVIEW_RESULT
date: YYYY-MM-DD
events_logged: N
journal_entries: M

TIMELINE:
| Time          | Source     | Event                              |
|---------------|------------|-------------------------------------|
| HH:MM–HH:MM   | DB         | "Event Title" (type)               |
| HH:MM–HH:MM   | DB+Garmin  | "Event Title" [Garmin ID: xxx]     |
| HH:MM–??      | ?          | MISSING (~N min) — please fill     |
...

GAPS (> gap_threshold_minutes):
- HH:MM–HH:MM: N min unlogged

GARMIN_STATUS:
- "Activity Name" HH:MM (N min) → matched to "DB Event Title" | UNLINKED

GARMIN_SUMMARY:
- Sleep: HH:MM–HH:MM (Xh Ym), BB at wake: N
- BB end of day: N

SUMMARY:
- Events logged: N
- Gaps detected: M (total ~Xh Ym unlogged)
- Garmin activities: X/Y linked
```

**Do NOT log anything in CONTEXT mode.** Return only, no writes.
