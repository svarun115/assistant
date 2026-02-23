# Kusto — Retro Context

Skill-specific context for `/retro kusto` sessions.

---

## GitHub Issue Repos

| Server | Repo | Labels |
|--------|------|--------|
| Kusto MCP | Microsoft Agency CLI (internal) | File via `agency` feedback or internal channels |

---

## Skill-Specific Retro Notes

Common root causes in kusto sessions:

- **Wrong field**: Database "PrettyName" != actual DatabaseName — must call `list_databases` first
- **Data overflow**: KQL queries returning too many rows for context window
- **Sunk cost**: Iterating on query syntax instead of checking table schema first
