# Expenses — Retro Context

Skill-specific context for `/retro expenses` sessions.

---

## GitHub Issue Repos

| Server | Repo | Labels |
|--------|------|--------|
| Google Workspace (Sheets) | `svarun115/google-workspace-mcp-server` | `bug`, `enhancement` |

Splitwise uses a third-party MCP server — file issues on its upstream repo if encountered.

---

## Skill-Specific Retro Notes

Common root causes in expenses sessions:

- **Wrong field**: Spreadsheet column references or Splitwise API field mismatches
- **Data overflow**: Large bank statement parsing producing too many rows for context
- **Shell/platform**: CSV/date format parsing differences on Windows
