# Daily Tracker — Retro Context

Skill-specific context for `/retro daily-tracker` sessions.

---

## GitHub Issue Repos

| Server | Repo | Labels |
|--------|------|--------|
| Google Workspace | `svarun115/google-workspace-mcp-server` | `bug`, `enhancement` |
| Garmin | `svarun115/garmin-mcp-server` | `bug`, `enhancement` |
| Journal DB | `svarun115/journal-db-mcp-server` | `bug`, `enhancement` |

Journal and Garmin issues are typically filed during `/retro journal` — only file here if the issue is specific to daily-tracker's usage pattern (e.g., parallel call failures, cache interactions).

---

## Skill-Specific Retro Notes

Common root causes in daily-tracker sessions:

- **MCP isolation**: Google Workspace calls batched with journal/Garmin calls — auth failure cascades and kills siblings
- **Redundant calls**: Re-querying journal state that the journal agent already fetched
- **Sunk cost**: Retrying failed Google Workspace auth instead of noting it and moving on
- **Intent detection**: Misidentifying TRACK vs PLAN vs VIEW mode from ambiguous user messages
