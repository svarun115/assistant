# Deployment Model

## Docker Compose services
```
assistant         port 8080  (external)   journal-processor/agent-orchestrator
journal-mcp       port 3333  (internal)   db-mcp-server
garmin            port 5555  (internal)   garmin-mcp-server
google-workspace  port 3000  (internal)   google-workspace-mcp-server
google-places     port 1111  (internal)   googleplaces-mcp-server
splitwise         port 4000  (internal)   splitwise-mcp-server
```
MCP servers: no external ports. Docker service names used for inter-container URLs.

## Key env vars (.env.production)
```
ASSISTANT_API_KEY              Gateway auth key (SHA-256 stored in api_keys table)
CREDENTIALS_ENCRYPTION_KEY     64 hex chars (32 bytes) for AES-256-GCM
SYSTEM_DB_URL                  postgresql://...@.../assistant_system?sslmode=require
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY              Operator key (fallback when allow_operator_llm=TRUE)
OPENAI_API_KEY                 For distillation model
DB_HOST / DB_USER / DB_PASSWORD For journal-mcp (varun_journal)
GARMIN_EMAIL / GARMIN_PASSWORD
GOOGLE_PLACES_API_KEY
MCP_JOURNAL_URL / MCP_GARMIN_URL / MCP_GOOGLE_URL / MCP_PLACES_URL / MCP_SPLITWISE_URL
  (override from Docker service names — set in docker-compose.yml environment block)
```

## Volumes
```
garmin-tokens      → /app/.garth           (garmin session tokens)
assistant-sqlite   → /app/sqlite           (ThreadManager SQLite fallback)
~/.claude/skills/  → /app/skills:ro        (task skills)
~/.claude/data/    → /app/data:ro          (user-context.md, daily-context.json)
./tokens/          → OAuth token files     (google credentials)
```

## What's in the Docker image vs. what's not
| Path | In image? | Why |
|---|---|---|
| `system-agents/` | Yes | System agents ship with the service |
| `agents/` | No | User agent definitions seeded to DB during setup |
| `skills/` | No | Mounted as volume from host |
| `.env*` | No | Secrets |
| `*.db` | No | State files (volumes or PG) |
| `migrations/` | Yes | Included for reference, but not run at startup |

## Setup sequence (new deployment)
```bash
# 1. Create assistant_system DB and schema
python migrations/run_create_assistant_system.py

# 2. Create api_keys table + seed default user key
python migrations/run_add_api_keys.py

# 3. Create agent system tables
python migrations/run_add_agent_system.py

# 4. Seed user agent templates (cos, financial-advisor, fitness-coach)
python migrations/run_seed_agent_templates.py

# 5. Seed COS-level schedules (daily-planner, email-triage, retro, expenses-reminder)
python migrations/seed_schedules.py

# 6. Deploy
docker-compose up -d
```

Note: agent schedules for user agents (fitness-coach-weekly, financial-advisor-weekly)
are seeded automatically by `AgentScheduler.sync_from_heartbeats()` when those
agent instances are created (during user setup/bootstrap).

## Azure infrastructure
- VM: B2s (~$30/month) — 2 vCPUs, 4GB
- PostgreSQL: Flexible Server (~$15-25/month) — varun_journal + assistant_system
- Nginx reverse proxy → Let's Encrypt TLS → port 8080
- LLM API: ~$20-50/month (Sonnet + Haiku distillation)
