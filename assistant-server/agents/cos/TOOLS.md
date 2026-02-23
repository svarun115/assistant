---
allowed_servers: []  # COS has unrestricted access to all connected MCP servers
---

# COS Tool Access

COS is the orchestrator and has unrestricted access to all connected MCP servers.

It uses tools from:
- `journal-db` — querying journal state, checking recent events
- `garmin` — quick fitness/recovery status queries
- `google-workspace` — calendar, upcoming meetings
- `google-places` — location context
- `splitwise` — expense status

COS does NOT do deep work with these tools — it delegates to specialists.
Quick lookups (e.g. "what's on my calendar today?") are fine inline.
