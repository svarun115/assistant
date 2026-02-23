# SETUP Mode

Full context gather for the first invocation of the day.

## Step 1: Parallel State Fetch

Launch these in parallel:

**1a. Journal agent (background):**
Check `agent.journal_agent_id` and `agent.journal_agent_date` in `~/.claude/data/daily-context.json`:
- Date matches today → Resume in **REFRESH mode**
- Date mismatch or missing → Spawn in **SETUP mode**

```
mode: "SETUP"
entry_date: "<today>"
context:
  owner_id: "<from daily-context.json owner.id>"
  location_id: "<from daily-context.json location.id>"
  people_at_location: <from daily-context.json people_at_location>
  entity_cache: <from daily-context.json entity_cache>
```

Capture the agent ID. Write `agent.journal_agent_id` and `agent.journal_agent_date` to `daily-context.json`.

**1b. Google Calendar** — today's events (and tomorrow if after 6 PM):
- `start_date: "YYYY-MM-DD"`, `end_date: "YYYY-MM-DD+1"` — end_date is EXCLUSIVE, always add 1 day

**1c. Google Tasks — ALL lists:**
1. `list_tasklists` first
2. Fetch all lists in parallel (skip Movies, TV Shows, Books)
3. Fetch all open tasks per list (no date filter)
4. After receiving results:
   - **Overdue + today** tasks → will populate `daily-plan.md` Today's TODOs section (Step 4a below)
   - **Scan notes** for `Deadline: YYYY-MM-DD` — surface as urgent if deadline is today or tomorrow, regardless of scheduled (`due`) date
   - **Retain task IDs in memory** for the session (needed for `complete_task` / `update_task` calls at check-in and wrap-up)

**1d. WorkIQ** (optional): `workiq ask -q "What meetings do I have today?"` — skip if unavailable

**1e. Email scan (chat display only — only triage timestamp is cached):**
1. Read `triage.last_email_triage` from `daily-context.json`
2. If today → skip. If stale/missing → scan (cap at 7 days)
3. Run in parallel:
   - `search_emails(query="is:unread category:primary", max_results=20)`
   - `search_emails(query="category:primary -label:sent", max_results=20)`
4. Deduplicate by ID. Classify: **needs action** vs **FYI**
5. For "needs action": check `in:sent to:{sender}` — if replied, reclassify as "Waiting"
6. Update `triage.last_email_triage` in `daily-context.json` to today

**1f. People at location:**
Check `people_at_location` in `daily-context.json`.
- If populated and location matches → use as-is, pass to journal agent
- If empty → ask user: "Who's currently staying at [location]?" then write to `daily-context.json`

Google Workspace calls (1b, 1c, 1e) run in the main thread. Journal + Garmin run inside the journal agent subagent — safe to run concurrently.

## Step 2: Wait for Journal Agent + Assemble State

When journal agent completes (`TaskOutput`), read its `QUICK_LOG_STATE_READY` bundle. The bundle is the source of truth — it always contains today's events, active health, journal gaps, recent days' events, Garmin summary, and any newly resolved entities. No extraction spec needed; just use what's returned.

**Write-back to `daily-context.json`** after receiving the bundle:
- `garmin.date`, `garmin.wake_time`, `garmin.body_battery_at_wake`, `garmin.resting_hr`, `garmin.sleep_hours` — from bundle's Garmin section
- `entity_cache.recent_people`, `entity_cache.recent_locations` — merge `new_entities` from bundle into existing cache

## Step 2.5: Cross-Reference Overdue Tasks Against Recent Events

Before surfacing any overdue task in chat, check `recent_days_events` from the bundle:
- If a task like "Prep for X" or "Do X" is overdue AND a matching event appears in recent days → it's likely done — skip it or confirm with user
- This is reasoning only — never written to any file

## Step 3: Calculate Unlogged Gaps

Using `today_events` from bundle + `garmin.wake_time`:
- Flag gaps > 30 min between wake time and now as `[unlogged]`

**Calendar events are scheduled, not confirmed.** Do NOT list a calendar event as having occurred unless:
1. A matching journal event exists for that time, OR
2. A matching Garmin activity exists (for workout/fitness events), OR
3. The user confirms it happened

For past calendar events with no corroboration:
- Workout/fitness events: if no Garmin activity and wake time is after the event start → mark as **[skipped?]**
- Other events: list as **[calendar — confirm?]** and ask the user

## Step 4: Write `daily-plan.md`, Then Brief Chat Summary

### 4a. Write `~/.claude/data/daily-plan.md`

```markdown
---
date: YYYY-MM-DD
location: [current location name]
---

# [Weekday, Month DD]

**[HH:MM] | [Location]** · *Updated [HH:MM]*
**Garmin:** Sleep [Xh Ym] · BB at wake: [N] → Current: [N] · RHR: [N] · Steps: [N]
**Health:** [active condition — X/10 with brief description — omit line if none]

---

## Timeline

| Time | Activity | Status |
|------|----------|--------|
| [wake] | Wake | done |
| [gap] | [unlogged ~Xh] | ? |
| ... | ... | ... |

---

## Today's TODOs
*(snapshot from Google Tasks — overdue + due today)*
- [ ] [task title] ([list name])

---

## Today's Plan
*(to be filled after gap logging)*

---

## Evening Review
*(to be filled at wrap-up)*
```

**Rules:**
- Health: active conditions only (no end_date, not noted as resolved). Use latest progression severity. Omit line if none.
- Timeline: confirmed events only. Calendar events marked `[skipped?]` or `[calendar — confirm?]` if unconfirmed.
- Today's TODOs: populated from Google Tasks (overdue + due today). This is a snapshot — Google Tasks is authoritative. Format: `- [ ] [task title] ([list name])` — add `⚠️ deadline: [date]` if task notes contain a `Deadline:` that's today or tomorrow.
- Email and journal gaps: surfaced in chat only — NEVER written to this file.

### 4b. Chat response — brief only

After writing the file, respond in chat with ONLY:
- One-liner: `**[HH:MM] | [Location] | Garmin:** Sleep Xh · BB N→N · RHR N`
- 1–2 urgent callouts from tasks/email — chat only. Flag: overdue items, things due today, critical action emails. Skip if nothing urgent.
- The gap question (Step 5)

## Step 5: Ask About Unlogged Gaps

Ask contextually — reference what was scheduled:
- Calendar events that occurred during the gap
- Recurring events (workouts, meetings)
- If nothing scheduled: "I see [X hours] since you woke — what have you been up to?"

Wait for user response before moving to PLAN mode.

## Step 6: Enter PLAN Mode

When user is ready to plan, read `plan-mode.md` and build the day's schedule.
On approval, write `daily-plan.md` — see `plan-mode.md` for the write step.
