# Shared — Journal Integration & Error Handling

Cross-cutting rules loaded in every mode. Keep these in mind throughout all daily-tracker flows.

## Journal Agent: Spawn vs. Resume

Always check `~/.claude/data/daily-context.json` for `journal_agent_id` and `journal_agent_date` before spawning:

| Condition | Action |
|-----------|--------|
| `journal_agent_date` matches today + agent ID exists | **Resume** — pass `resume: <journal_agent_id>` |
| Date mismatch or missing | **Spawn** — new agent, save returned ID + today's date |

After spawning, write the new `journal_agent_id` and `journal_agent_date` (today) to `daily-context.json`.

## Journal Agent: Always Background

All journal agent calls run with `run_in_background: true`. Never block the main thread waiting for a journal agent response — acknowledge the user immediately, then check agent output before the next response that depends on it.

## No Direct Journal MCP Calls — Zero Exceptions

Never call `mcp__personal-journal__*` directly from any daily-tracker mode. All journal interaction (reads, writes, entity resolution, state queries) flows through the journal agent.

**Why:** The journal agent has gotchas.md, entities.md, and logging.md loaded. Direct calls fail on datetime field formats and miss entity linking. There is no "quick read" exception.

## MCP Isolation

Google Workspace (Calendar, Tasks, Gmail) shares a single auth context — if one fails, all fail. Keep Google Workspace calls in their own parallel block, separate from journal/Garmin calls.

Journal and Garmin calls run inside the journal agent subagent (separate execution context), so they're safe to run concurrently with Google Workspace in the main thread.

## Error Handling

### MCP Server Unavailable

One attempt max for any MCP server. If it fails:
- Note the failure briefly ("Garmin unavailable — skipping")
- Continue with what you have
- Don't retry the same call
- Don't ask the user to wait while you retry

### Tool/Query Failures

If a query fails (wrong format, unexpected response):
- Don't retry with the same call
- Pivot to an alternative (different query, ask user, infer from context)
- If it's a journal query: the journal agent has gotchas.md — route through the agent next time

### Google Workspace Auth Failure

If any Google Workspace call fails with an auth error, all Google calls are likely broken. Stop Google calls for the session and note it to the user. Don't cascade attempts.

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
- Email triage run → write `last_email_triage`
- Location changes → write `location.current`

Minimize writes — only update fields that actually changed.
