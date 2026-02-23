# Journal Agent — INIT / REFRESH State

Handles first invocation (INIT) and resumed state refresh (REFRESH).

---

## Step 1: Load Skill Files (SETUP only)

Use the `context` input directly — all cache data is pre-loaded:
- `context.owner_id`, `context.location_id`, `context.people_at_location`
- `context.entity_cache.recent_people`, `context.entity_cache.recent_locations`

**On SETUP**, read these journal skill files in parallel:
- `~/.claude/skills/journal/logging.md` — event creation rules
- `~/.claude/skills/journal/gotchas.md` — query field tables, enum values, known bugs
- `~/.claude/skills/journal/entities.md` — entity resolution rules
- `~/.claude/skills/journal/errata.md` — active known issues and mistakes to avoid

**On REFRESH**: skip skill file loading — already in context. Proceed directly to Step 2.

---

## Step 2: Gather Journal State

### SETUP — Run all queries in parallel

**Query 1: Today's Events**
```
query(entity="events", where={date: "<entry_date>"}, orderBy="start", orderDir="asc", limit=200)
```

**Query 2: Active Health Conditions + Latest Progression**
```
query(entity="health_conditions", where={end_date: {isNull: true}}, limit=50)
query(entity="health_condition_logs", where={condition_id: {in: [<ids from above>]}}, orderBy="log_date", orderDir="desc", limit=5 per condition)
```
Use the most recent progression log severity — not the base condition's initial severity.

**Query 3: Journal Gaps (Last 7 Days)**
```
aggregate(entity="events", where={date: {gte: "<7 days ago>", lte: "<yesterday>"}}, groupBy=["date"], aggregate={count: true})
```
Return: Dates with 0 events.

**Query 4: Recent Days' Events**
```
query(entity="events", where={date: {gte: "<2 days ago>", lte: "<yesterday>"}}, orderBy="start", orderDir="asc", limit=100)
```
Return: Event titles/types/times for yesterday + day-before (for caller's overdue task cross-referencing).

**Query 5: Today's Journal Entries**
```
query(entity="journal_entries", where={entry_date: "<entry_date>"}, orderBy="created_at", orderDir="asc", limit=50)
```

**Garmin (SETUP):**
```
get_user_summary(date: "<entry_date>")
get_activities_by_date(start_date: "<entry_date>", end_date: "<entry_date>")
```

---

### REFRESH — Run minimal queries only

**Query 1: Today's Events** (same as above — get full current list)

**Query 2: Today's Journal Entries**
```
query(entity="journal_entries", where={entry_date: "<entry_date>"}, orderBy="created_at", orderDir="asc", limit=50)
```
Include entries from /done and /journal skills — these are text logs, not structured events. Include them so the caller can see activity logged via other sessions.

**Garmin:**
```
get_user_summary(date: "<entry_date>")
```
Current Body Battery and steps only.

Skip Queries 2–4 from SETUP — health/gaps/recent-days not needed for check-in.

---

## Step 3: Return State Bundle

```
QUICK_LOG_STATE_READY
- Today's events: N
  - [HH:MM–HH:MM] "Title" — type/subtype at Location
  - ...
- Today's journal entries: M
  - [entry_id] "excerpt..." — type, tags
  - ...
- Active health: M  (SETUP only)
  - "Condition" (severity X/10 from latest log, since date)
  - ...
- Journal gaps (last 7 days): [none | list of dates]  (SETUP only)
- Recent days' events (yesterday + day-before):  (SETUP only)
  - [YYYY-MM-DD] HH:MM–HH:MM "Title" — type
  - ...
- Garmin: Sleep Xh Ym · BB at wake: N → current: N · RHR: N · Steps: N · Activities: [none | list]
- New entities: { people: [], locations: [] }
- Ready to log: [waiting for activities | or proceed if events provided]
```

If new activities are provided in the input alongside SETUP/REFRESH, continue to the LOG mode file (`~/.claude/agents/journal-agent/log.md`) immediately after returning the bundle.
