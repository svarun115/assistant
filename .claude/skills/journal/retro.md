# Journal — Retro Context

Skill-specific context for `/retro journal` sessions.

---

## GitHub Issue Repos

| Server | Repo | Labels |
|--------|------|--------|
| Journal DB | `svarun115/journal-db-mcp-server` | `bug`, `enhancement` |
| Garmin | `svarun115/garmin-mcp-server` | `bug`, `enhancement` |
| Google Places | `svarun115/google-places-mcp-server` | `bug`, `enhancement` |

Use the GitHub MCP server (`mcp__github-mcp__create_issue`) to file issues.

---

## Issue Tracker

### Open Bugs

*No open bugs.*

### Pending Enhancements

1. **[#72](https://github.com/svarun115/journal-db-mcp-server/issues/72)** - Add authentication-based environment access control
   - Labels: `enhancement`, `security`
   - Created: Nov 20, 2025

### Recently Resolved

- #124 - `in`/`notIn` operators fail with date fields (Fixed 2026-02-15)
- #123 - `query` tool fails with nested where clauses (Fixed 2026-02-15)
- #122 - `update_health_condition_log` missing arguments parameter (Fixed 2026-02-15)
- #121 - Add `person_id` to health_conditions for non-owner tracking (Completed 2026-02-15)
- #120 - `update_health_condition` end_date parsing fails (Fixed 2026-02-15)
- #119 - `delete_health_condition_log` missing arguments parameter (Fixed 2026-02-15)

---

## Skill-Specific Retro Notes

Common root causes in journal sessions:

- **Wrong entity**: Querying `specializations` instead of `events`, or `health_condition_logs` vs `health_conditions`
- **Wrong field**: Using `start_time` instead of `start`, `entry_date` instead of `date`
- **Missing hydration**: Include not returning expected nested participants/locations
- **Data overflow**: Unbounded queries returning too many events for context window
