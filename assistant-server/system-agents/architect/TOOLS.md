---
allowed_servers:
  - journal-db
---

# Architect Tool Access

The Architect has read-only access to `journal-db` for system introspection.

Primary use: query `assistant_system` tables to understand current state
(what agents are installed, what schedules exist, what notifications are pending).

The Architect does NOT write to any MCP server directly. All writes are done
by COS after the Architect provides instructions.

Note: The Architect uses `execute_sql_query` on journal-db (which has access
to assistant_system tables via the same PostgreSQL server) for read-only
system state queries.
