# Daily Tracker — Errata & Improvements

Tracking tool call mistakes made during daily-tracker sessions. Improvements are graduated to [SKILL.md](SKILL.md) once validated.

---

## Active Rules

### Rule 15: Google Tasks is the source of truth for task persistence (High)
**Added:** 2026-02-21

**Problem:** Tasks were maintained in two places — `daily-plan.md` "Punted to Tomorrow" section AND Google Tasks — with no sync between them. This caused drift: tasks that were rescheduled in Google Tasks didn't update the plan file, and tasks written to the plan file weren't always in Google Tasks. The `due` field was also used interchangeably for "scheduled date" and "hard deadline," making it impossible to distinguish the two.

**Changes made:**
- `user-prefs.md`: Added "Task Persistence Model" section defining Google Tasks as source of truth and the two-date convention (`due` = scheduled date, `notes: Deadline: YYYY-MM-DD` = hard deadline)
- `setup.md`: Step 1c now writes overdue/today tasks to `daily-plan.md` Today's TODOs + scans notes for deadlines; task IDs retained in session memory
- `plan-mode.md`: Removed "Punted to Tomorrow" section from template; Today's TODOs is now a Google Tasks snapshot; added "never re-add manually" rule
- `task-mode.md`: Added two-date model to task creation and rescheduling flows
- `wrapup.md`: Step 4 clarified to update Google Tasks `due` only (not modify `Deadline:` notes); Step 6 preview now fetches tomorrow's Google Tasks

**Rule:** `daily-plan.md` Today's TODOs is a read-only snapshot populated during SETUP. All task persistence flows through Google Tasks. No "Punted to Tomorrow" sections. Pushing a task forward = updating its `due` date in Google Tasks.

---

### Rule 14: Sync Today's TODOs checkboxes when marking plan items done (High)
**Added:** 2026-02-20

**Problem:** When marking MOSL beneficiary task as done, updated the Timeline row status and called `update_plan_item`, but did NOT check off the corresponding `- [ ]` item in the Today's TODOs section of `daily-plan.md`. The two sections are independent parts of the file with no automatic sync.

**Rule:** Whenever marking any plan item done (Timeline row → `done`, `update_plan_item` called), also scan the Today's TODOs section and check the matching item `- [x]`. Both sections must be updated atomically.

**Added to:** `shared.md` → Cross-System Follow-Through table.

---

### Rule 12: Unified Journal Agent Architecture
**Added:** 2026-02-15

All journal interaction (reads, writes, entity resolution) now flows through a single persistent journal agent. The quick-log agent was renamed to journal-agent and enhanced with state-gathering modes (SETUP/REFRESH). This eliminates the separate entity agent and consolidates all journal operations.

**Changes:**
- Deleted: `~/.claude/agents/entity-agent.md` (redundant)
- Renamed: `quick-log-agent.md` → `journal-agent.md`
- Updated: daily-tracker Step 1 to spawn journal agent in SETUP/REFRESH mode
- Updated: All skills to delegate all journal operations to journal-agent
- Removed: Exception rule allowing direct journal queries in daily-tracker

### Rule 13: No direct journal MCP calls — zero exceptions (High)
**Added:** 2026-02-16

**Problem:** In the Feb 16 daily-tracker session, called `mcp__personal-journal__*` tools directly 10 times instead of routing through the journal agent. Rationalized as "faster for quick reads." Two of those calls failed with wrong datetime format for the `start` field — a format the journal agent knows from gotchas.md but the main agent doesn't.

**Incident:** 10 direct calls (query events, aggregate gaps, query health_conditions, query journal_entries). 2 failed with `QUERY_ERROR: invalid input for query argument` on datetime string format. The journal agent has gotchas.md loaded which documents correct field types and common mistakes.

**Rule:** NEVER call `mcp__personal-journal__*` directly from daily-tracker. ALL journal reads and writes go through the journal agent — including "simple" reads. The agent has context (gotchas.md, entities.md, logging.md) that prevents format errors and ensures consistent entity resolution. There is no "quick read" exception.

**Why this matters beyond architecture:** The main agent lacks journal field format knowledge. Direct calls are not actually faster when they fail and need debugging. The journal agent's loaded context is the practical reason for delegation, not just organizational cleanliness.

---

## Graduated Rules

### Rule 1 → SKILL.md: Validate stale cache with recent journal events
**Added:** 2026-02-13 | **Graduated:** 2026-02-15

When cache date != today, query recent journal events to validate cache assumptions. Added to Step 1a cache logic.

### Rule 2 → SKILL.md: Always fetch active health conditions on invocation
**Added:** 2026-02-13 | **Graduated:** 2026-02-13

Added step 1f to fetch open `health_conditions` in the Step 1 parallel block.

### Rule 3 → SKILL.md: Isolate Google Workspace from critical queries
**Added:** 2026-02-13 | **Graduated:** 2026-02-13 | **Updated:** 2026-02-14

MCP isolation rule: Google Workspace calls run in a separate sequential call after the critical batch.

### Rule 4 → SKILL.md: Delegate ALL journal write operations to quick-log agent
**Added:** 2026-02-13 | **Graduated:** 2026-02-13

Added "Delegation Principle" section to Journal Integration.

### Rule 5 → SKILL.md: Never batch calls to untested tools in same parallel block
**Added:** 2026-02-13 | **Graduated:** 2026-02-15

Added to Error Handling → Query/Tool Failures section.

### Rule 6 → SKILL.md: Always check system time — never assume
**Added:** 2026-02-13 | **Graduated:** 2026-02-13

Added Step 0 to SKILL.md — mandatory system time check.

### Rule 7 → SKILL.md: Proactively complete Google Tasks on cross-system triggers
**Added:** 2026-02-14 | **Graduated:** 2026-02-15

Added as concrete example to Non-Negotiable #9 (cross-system follow-through).

### Rule 8 → SKILL.md: One attempt max for non-responding services
**Added:** 2026-02-14 | **Graduated:** 2026-02-15

Expanded Error Handling → MCP Server Unavailable with "one attempt max" guidance.

### Rule 9 → SKILL.md: Auto-fetch gap data on every check-in
**Added:** 2026-02-14 | **Graduated:** 2026-02-14

Added gap scan table to Step 0 in SKILL.md.

### Rule 10 → SKILL.md: Pivot immediately on server query failures
**Added:** 2026-02-15 | **Graduated:** 2026-02-15

Added to Error Handling → Query/Tool Failures section. Root cause (bug #123) also fixed.

### Rule 11 → CLAUDE.md: Check MCP config before filesystem/GitHub searches
**Added:** 2026-02-15 | **Graduated:** 2026-02-15

Added to CLAUDE.md Quick Reference as "MCP Server Discovery" tip (applies to all skills).
