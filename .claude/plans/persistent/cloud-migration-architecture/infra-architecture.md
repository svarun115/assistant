# Shared Infrastructure Architecture

Foundation that all assistant profiles (personal, work, future) build on.

---

## Architecture

```
Any client (browser, iPhone Safari, Telegram, PWA, iPhone sensor app)
    │  HTTPS + WebSocket  (API key auth)
    ▼
Azure VM
  ┌──────────────────────────────────────────────┐
  │  journal-processor  (FastAPI + WebSocket)     │
  │  - Profile-based config                       │
  │  - Skill router → active skill system prompt  │
  │  - LangGraph orchestration (per-thread state) │
  │  - MCP bridge (tool discovery + routing)      │
  │  - Multi-agent: COS / task / background /     │
  │    foreground agent spawner                   │
  │  - COS nervous system (scheduler + notif)     │
  │  - Web UI (static/ — chat + daily plan)       │
  │  - Auth middleware                            │
  └──────────────────────┬───────────────────────┘
                         │
         ┌───────────────┼──────────────────┐
         ▼               ▼                  ▼
    Personal MCP     Work MCP            Other MCP
    (per profile)    (per profile)       (per profile)
         │
         ▼
Azure PostgreSQL  (same server, two databases)
  ├── varun_journal   — personal data, per-profile, never shared
  └── assistant_system — infra state, shared + RLS, user_id on every row
```

---

## Current State (2026-02-22)

### Databases
- `varun_journal` — personal data (events, workouts, meals, journal entries, 405+ rows, pgvector embeddings)
- `assistant_system` — infra state (threads, scheduler, notifications, artifacts, agent_templates, agent_instances, api_keys, user_credentials, cos_trust_registry — all with RLS)
- Azure PostgreSQL Flexible Server, PITR backups, 7-day retention

### Gateway codebase
`C:\Users\vasashid\AI Projects\Assistant\journal-processor\agent-orchestrator\`

| Component | Status | Notes |
|---|---|---|
| FastAPI + WebSocket server | ✅ | `web_server.py` — HTTP + streaming WS |
| LangGraph orchestration | ✅ | `graph/` — PostgreSQL checkpoints, per-thread state |
| MCP bridge | ✅ | `mcp_bridge.py` — per-user bridges via `BridgeManager` |
| Multi-model LLM | ✅ | Claude, OpenAI, Ollama; BYOK via `CredentialStore` |
| Context distillation | ✅ | Compresses old messages; separate distillation model |
| Skill router | ✅ | Slash commands, session persistence, intent detection |
| Tool isolation | ✅ | `to_filtered_tools()`, `SKILL_ALLOWED_SERVERS` per skill |
| User context injection | ✅ | `user-context.md` + `daily-context.json` → every agent |
| `AssistantProfile` | ✅ | `profile.py` — all config from env vars, no hardcoding |
| Authentication | ✅ | `api_keys` table, SHA-256 hashed, roles: personal/admin/cos_internal |
| Credential encryption | ✅ | `credential_store.py` — AES-256-GCM, `user_credentials` table |
| Per-user MCP bridge | ✅ | `bridge_manager.py` — user creds injected as HTTP headers |
| BYOK | ✅ | `llm_anthropic` / `llm_openai` in `user_credentials`; `allow_operator_llm` gate |
| Agent system | ✅ | `agent_loader.py` — DB-backed templates + instances; system-agents/ |
| Agent spawner | ✅ | `agent_spawner.py` — task / background / foreground |
| Scheduler | ✅ | `scheduler.py` — 60s polling, heartbeat-driven schedule sync |
| Notification queue | ✅ | `notification_queue.py` — WebSocket push + artifact store |
| State persistence | ✅ | PostgreSQL (production), SQLite fallback (local dev) |
| Docker + docker-compose | ✅ | 6 services, `.env.production.example`, `.dockerignore` |
| VM deployment | ⏳ | Azure B2s, Nginx + TLS — not yet provisioned |
| Web UI | ⏳ | Bootstrap flow, daily plan panel, mobile — not yet built |

### MCP servers (5 personal)
All Dockerized. Communicate via Docker service names in production.

---

## Design Principles

### Profile-based configuration

Everything that varies between assistant instances lives in a **Profile**. Never hardcoded.

```python
@dataclass
class AssistantProfile:
    name: str                           # "personal", "work"
    mcp_servers: list[MCPServerConfig]  # which tool servers to connect
    journal_db_url: str                 # personal data DB (varun_journal, work_journal, etc.)
    system_db_url: str                  # infra DB (assistant_system — shared)
    skills_dir: Path                    # which skills to load
    user_context_path: Path             # user-context.md location
    allowed_skills: list[str] | None    # skill whitelist, or None for all
    llm_config: LLMConfig               # model + API key
    journal_features: list[str]         # future: ["fitness", "meals", "expenses", "health"]
    cross_cos_trust: dict[str, TrustLevel]  # future: trusted COS IDs + their access level
    share_policy: SharePolicy           # future: what this COS exports when asked
```

**Rule:** Every component receives `profile: AssistantProfile` and reads all config from it. Nothing hardcodes DB URLs, MCP server addresses, or skills paths.

**Multi-user affordances (design now, build later):**
1. `user_id` column on every `assistant_system` table — one constant today, filter later
2. Auth middleware returns a `Profile` object (not just allowed/denied) — single key → profile today, JWT → profile lookup tomorrow
3. Profile-relative paths only (`profile.user_context_path`, not `Path.home()`) — already done in `SkillsLoader`
4. `user_id` on WebSocket sessions — route notifications correctly when multi-user comes

### Database separation

Two databases on the same Azure PostgreSQL server (no extra cost):

| Database | Pattern | Retention | Why |
|---|---|---|---|
| `varun_journal` (was `assistant_dev`) | **Separate DB per profile** | Forever | Personal data — health, finances, relationships. No cross-profile exposure ever. Schema evolves per person. |
| `assistant_system` | **Shared + `user_id` + RLS** | Short-lived OK | Infra state — threads, scheduler, notifications. One DB to manage, migrate, backup. DB-enforced isolation. |

```sql
-- PostgreSQL RLS on assistant_system — enforced at DB level, not application level
ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduler ENABLE ROW LEVEL SECURITY;
-- ... all system tables

CREATE POLICY user_isolation ON threads
    USING (user_id = current_setting('app.user_id')::text);

-- Gateway sets at connection time:
SET app.user_id = 'varun';
```

**Naming:** `assistant_dev` → `varun_journal` as part of Phase 1.
`ALTER DATABASE assistant_dev RENAME TO varun_journal;`

**Future: user-configurable schema.** `profile.journal_features` controls which tables are initialized. Phase 5+ work; the hook exists now.

### Multi-agent architecture

Four agent types with distinct UX contracts:

| Type | User-facing | Lifetime | Invoked by |
|---|---|---|---|
| **COS** (Chief of Staff) | Yes — primary thread | Always-on | User directly |
| **Foreground agent** | Yes — user switches to it | Until dismissed | COS (pre-warmed) or user |
| **Background agent** | No — delivers artifact to COS | Scheduled/event-driven | Scheduler or COS |
| **Task agent** | No — returns result to COS | Ephemeral | COS (inline sub-task) |

**Communication rule:** User talks only to COS or a foreground agent COS handed off to. All other agents are invisible. Cross-COS: COS A talks to COS B, never to COS B's agents.

**COS:**
- Always-on primary thread; full context (identity, daily plan, active/scheduled agents)
- Can answer directly, spawn any agent type, or hand off to foreground agent
- Proactively notifies; manages artifact store (daily_plan, email digest, etc.)
- Single point of contact for all inter-agent communication visible to user

**COS nervous system (how always-on works):**

COS doesn't run 24/7 as an LLM process. It's event-driven — wakes up when there's something to do.

```
assistant_system PostgreSQL (always running)
  ├── scheduler    { user_id, skill, cron, next_run, config }
  ├── notifications { user_id, from_agent, to_cos_thread, message, priority, read_at }
  └── artifacts    { user_id, type, content, agent_id, created_at }

Background process (asyncio task alongside FastAPI — truly always on)
  ├── Scheduler tick — every 60s:
  │     Fire due background agents
  │     Pre-warm foreground agents at scheduled times
  │
  ├── Notification dispatcher:
  │     Agent completes → writes to notifications → pushes to open WebSocket
  │     No client open → queues for Telegram/APNs
  │
  └── Urgency triage — every 5 min (cheap LLM call):
        Unread urgent notifications? → Wake COS briefly
        COS decides: interrupt user or hold until next check-in
```

Delivery channels: WebSocket (Phase 1) → Telegram (Phase 4) → APNs (Phase 5+)

### Cross-COS federation (future, design now)

COS instances across profiles — and eventually across people — share availability via **curated exports**, not raw data.

```python
class TrustLevel(Enum):
    AVAILABILITY_ONLY   # free/busy only — "blocked 9-11am"
    CONTEXT_AWARE       # priorities, energy, rough themes
    FULL_COLLABORATION  # same-person personal↔work: near-full context

class SharePolicy:
    can_share_calendar: bool
    can_share_priorities: bool
    can_share_stress_level: bool
    blackout_topics: list[str]  # never export: health, finances, family
```

COS B returns a curated summary based on its `share_policy` — never raw data. Work COS knows you're blocked Thursday morning, not why.

For person↔person: mutual trust registry consent required (both sides opt in).

Infrastructure: `cos_trust_registry` table in `assistant_system`; notification queue has `from_cos_id` for cross-instance routing.

---

## ✅ Phase 0: pgvector Migration — COMPLETE (2026-02-22)

Eliminated local ChromaDB. All 377 journal embeddings live in Azure PostgreSQL (varun_journal).

**Changes made:**
- `azure.extensions` → added `VECTOR`; extension enabled
- `migrations/add_pgvector_embeddings.sql` — `embedding vector(384)` column + IVFFlat index
- `services/memory_service.py` — rewritten: ChromaDB → pgvector queries via asyncpg
- `database.py` — pgvector codec registered per-connection
- `config.py` — `MemoryConfig` stripped of ChromaDB fields
- `container.py` — passes `db` to `MemoryService`
- `requirements.txt` — `chromadb` → `pgvector`
- `migrate_chroma_to_pgvector.py` — one-time migration (377/377, 0 errors)
- 5 backup MCP tools removed; dead restore code deleted; `dump_sql.py`, `dump_json.py` added

**Verified:** `embedding IS NULL AND is_deleted = FALSE` → **0**

---

## ✅ Phase 1: Cloud Deployment — COMPLETE except 1g (2026-02-22)

**Goal:** Gateway running on Azure VM, accessible from any device via HTTPS, with Profile system in place.

#### ✅ 1a. Rename `assistant_dev` → `varun_journal`

Terminated 1 lingering connection, renamed via psycopg2 (no psql on machine).
Updated `db-mcp-server/.env.production`: `DB_NAME=varun_journal`. Verified 405 journal entries intact.

#### ✅ 1b. Create `assistant_system` DB + migrate LangGraph state from SQLite

- `assistant_system` created on Azure PostgreSQL
- Schema: `threads`, `scheduler`, `notifications`, `artifacts`, `cos_trust_registry`, `user_credentials` (all with RLS)
- Migration script: `migrations/create_assistant_system.sql` + `migrations/run_create_assistant_system.py`
- `langgraph-checkpoint-postgres`, `psycopg[binary]`, `psycopg-pool` added to `requirements.txt`
- `graph.py`: new `create_journal_graph_postgres()` using `AsyncPostgresSaver` + connection pool; `JournalGraph` handles pool cleanup
- `web_server.py`: uses PostgreSQL when `SYSTEM_DB_URL` is set, falls back to SQLite for local dev
- Thread metadata migrated: 57 threads → `assistant_system.threads` via `migrations/migrate_threads_to_postgres.py`
- **Note:** `ThreadManager` still uses SQLite (`journal_threads_meta.db`). `assistant_system.threads` is populated and ready; full ThreadManager PostgreSQL migration deferred to Phase 2 prep.

#### ✅ 1c. Build `AssistantProfile` + wire into gateway

- New `profile.py`: `AssistantProfile` dataclass + `build_personal_profile()` factory (reads all config from env vars, sensible dev defaults)
- `web_server.py`: 6 hardcoded values replaced — MCP servers, checkpoint path, threads path, API keys all come from profile
- `skills.py`: `SkillsLoader` accepts `data_dir` in constructor; fixed `"gmail"` → `"google-workspace"` in `SKILL_ALLOWED_SERVERS`

#### ✅ 1d. Add API key authentication

`APIKeyMiddleware` in `web_server.py` (Starlette `BaseHTTPMiddleware`):
- No-op when `ASSISTANT_API_KEY` unset (local dev)
- Enforces key via `X-API-Key` header or `?api_key=` query param
- `/static/*` and `/api/health` excluded

#### ✅ 1e. LLM configuration

All LLM config flows through `AssistantProfile.default_llm` (done as part of 1c).
`LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL` all read from env.

#### ✅ 1f. Dockerfiles + Docker Compose (completed 2026-02-23)

- 6 Dockerfiles: `assistant-server`, `db-mcp-server`, `garmin-mcp-server`, `google-workspace-mcp-server`, `googleplaces-mcp-server`, `splitwise-mcp-server`
- `docker-compose.yml` at `AI Projects/Assistant/` root — 6 services on `assistant-net` bridge; MCP servers internal-only (expose, not ports); gateway → :8080
- `.env.production.example` — all env vars documented with generation instructions
- `nginx/assistant.conf` — HTTP→HTTPS redirect + WebSocket upgrade; certbot-ready
- `deploy.sh` — idempotent deploy/update/logs/status/setup-docker/setup-nginx subcommands
- `assistant-server/Dockerfile` updated to COPY `agents/` + `system-agents/` (were missing)

**Service name → internal URL mapping (baked into docker-compose.yml):**
| Container | Internal URL |
|---|---|
| `journal-db` | `http://journal-db:3333/mcp` |
| `garmin` | `http://garmin:5555/mcp` |
| `google-workspace` | `http://google-workspace:3000/mcp` |
| `google-places` | `http://google-places:1111/mcp` |
| `splitwise` | `http://splitwise:4000/mcp` |

**Garmin tokens** persisted in `garmin-tokens` named volume. First-run auth via `GARMIN_EMAIL/PASSWORD`, then remove those vars.
**Google OAuth** tokens mounted from `./tokens/google/` (gitignored). `token.json` rw (refreshed at runtime), `credentials.json` ro.

#### ✅ 1h. Secrets cleanup

- Removed `GARMIN_EMAIL/PASSWORD` and `GOOGLE_PLACES_API_KEY` from `mcp-server-manager/servers.json` (redundant — services load their own `.env` files)
- Added `mcp-server-manager/.gitignore`

#### 1g. Azure VM setup — IN PROGRESS

**Done (local):** All deployment artifacts created (docker-compose.yml, .env.production.example, nginx/assistant.conf, deploy.sh).

**Remaining steps on the VM:**

```bash
# 1. Provision Azure B2s VM (Ubuntu 22.04 LTS) — ~$30/month
#    Open inbound ports: 22 (SSH), 80 (HTTP→redirect), 443 (HTTPS)

# 2. SSH in and install Docker
./deploy.sh setup-docker

# 3. Clone repo
git clone <repo-url> ~/assistant
cd ~/assistant

# 4. Clone .claude config (skills + data)
git clone <claude-config-repo-url> ~/.claude

# 5. Copy OAuth tokens from local machine
#    From local: scp tokens/google/token.json ubuntu@VM:/home/ubuntu/assistant/tokens/google/
#    From local: scp tokens/google/credentials.json ubuntu@VM:/home/ubuntu/assistant/tokens/google/

# 6. Fill in .env.production
cp .env.production.example .env.production
nano .env.production   # fill in all values

# 7. Deploy
./deploy.sh deploy

# 8. Install Nginx + TLS
./deploy.sh setup-nginx your-domain.com
sudo certbot --nginx -d your-domain.com

# 9. Verify
./deploy.sh status
curl -sf https://your-domain.com/api/health
```

**Note:** Garmin first-run auth — after first `./deploy.sh deploy`, verify the garmin container connected. If it didn't auto-authenticate from the named volume, run once with `GARMIN_EMAIL/PASSWORD` set, then remove them from `.env.production`.

---

## ✅ Phase 1.5: Multi-User Foundation — COMPLETE (2026-02-22)

**Goal:** Build the auth, credential, and per-session isolation primitives so every future feature is multi-user from day one. Single user today, zero refactoring when a second user arrives.

**Design principle:** user_id flows from auth → request context → bridge → DB. No component assumes a single user.

### Architecture

```
Client request (HTTPS/WebSocket)
    │  X-API-Key: sk_abc123...
    ▼
APIKeyMiddleware
    ├── SHA-256(key) → lookup api_keys table
    ├── Returns: user_id="varun", profile="personal"
    └── Attaches to request.state.user_id, request.state.profile_name
          │
          ▼
    ┌─────────────────────────────────┐
    │  BridgeManager                  │
    │  (cached per user_id)           │
    │                                 │
    │  user_id → MCPToolBridge        │
    │    ├── CredentialStore.get()     │
    │    │   → decrypt user tokens    │
    │    │   → inject as headers in   │
    │    │     MCPServerConfig         │
    │    └── connect to MCP servers   │
    │        with user-specific auth  │
    └─────────────────────────────────┘
          │
          ▼
    MCP Servers (garmin, google, etc.)
    ├── Request includes Authorization header per user
    └── MCP server acts on behalf of that specific user
```

### Roles via `profile_name`

`api_keys.profile_name` serves as the user role:

| profile_name | Who | Access |
|---|---|---|
| `personal` | Regular user | Accesses system only through COS |
| `admin` | Operator/superuser | Can invoke system agents directly, manage api_keys, view all users |
| `cos_internal` | COS acting as internal task caller | Trusted internal invocation of system agents |

The `admin` role unlocks: direct invocation of system agents (Architect), `api_keys` management, template upgrades, cross-user visibility.

### ✅ 1.5a. `api_keys` table + auth middleware upgrade

**Table:**
```sql
CREATE TABLE api_keys (
    key_hash        TEXT        PRIMARY KEY,       -- SHA-256 of the raw API key
    user_id         TEXT        NOT NULL,
    profile_name    TEXT        NOT NULL DEFAULT 'personal',
    label           TEXT,                          -- "varun's laptop", "iphone", etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used       TIMESTAMPTZ,
    is_revoked      BOOLEAN     NOT NULL DEFAULT FALSE
);
```

No RLS on this table — the middleware reads it before user_id is known. Index on `key_hash`.

**Middleware upgrade:**
- Hash incoming key with SHA-256
- Look up in `api_keys` (async DB query using gateway's PG pool)
- Attach `user_id` + `profile_name` to `request.state`
- **Fallback:** if `SYSTEM_DB_URL` is not set (local dev), fall back to string-compare against `ASSISTANT_API_KEY` env var with hardcoded `user_id="varun"` — preserves zero-config local dev
- **Migration:** on first startup with `SYSTEM_DB_URL` set and no `api_keys` rows, auto-seed from `ASSISTANT_API_KEY` env var for the default user

**Files:** `migrations/add_api_keys.sql`, `web_server.py` (middleware update)

### ✅ 1.5b. `CredentialStore` service

Encrypt/decrypt service backed by `user_credentials` table (already exists from Phase 1b).

```python
class CredentialStore:
    """Per-user credential vault backed by assistant_system.user_credentials."""

    def __init__(self, pg_pool, encryption_key: str):
        ...

    async def get(self, user_id: str, service: str) -> Optional[dict]:
        """Decrypt and return token_data JSON for a service, or None."""

    async def put(self, user_id: str, service: str, token_data: dict,
                  scopes: list[str] = None, expires_at: datetime = None):
        """Encrypt and upsert (INSERT ... ON CONFLICT UPDATE)."""

    async def delete(self, user_id: str, service: str):
        """Remove credential (revoke access)."""

    async def list_services(self, user_id: str) -> list[str]:
        """List services with stored credentials."""
```

**Encryption:** AES-256-GCM via Python `cryptography` library. Key from `CREDENTIALS_ENCRYPTION_KEY` env var. Each row has `encryption_key_id` for rotation — bump to `v2` when rotating, re-encrypt lazily on read.

**Files:** `credential_store.py` (new), `requirements.txt` (add `cryptography`)

### ✅ 1.5c. Per-session `MCPToolBridge` + `BridgeManager`

Currently `_mcp_bridge` is a global singleton in `web_server.py`. For multi-user, each user needs their own bridge with user-specific credentials injected as HTTP headers.

**`BridgeManager`:**
```python
class BridgeManager:
    """Manages per-user MCPToolBridge instances."""

    def __init__(self, base_servers: list[MCPServerConfig],
                 credential_store: Optional[CredentialStore]):
        self._bridges: dict[str, MCPToolBridge] = {}  # user_id → bridge
        self._base_servers = base_servers
        self._credential_store = credential_store

    async def get_bridge(self, user_id: str) -> MCPToolBridge:
        """Get or create a bridge for this user. Injects user credentials as headers."""
        if user_id in self._bridges and self._bridges[user_id].is_connected():
            return self._bridges[user_id]
        # Build MCPServerConfig list with user-specific headers
        servers = await self._build_user_servers(user_id)
        bridge = MCPToolBridge()
        await bridge.__aenter__()
        await bridge.connect(servers)
        self._bridges[user_id] = bridge
        return bridge

    async def _build_user_servers(self, user_id: str) -> list[MCPServerConfig]:
        """Clone base_servers with user-specific auth headers from CredentialStore."""
        ...

    async def cleanup(self):
        """Shut down all bridges."""
```

**Credential → header mapping** (per MCP server):
| MCP Server | user_credentials.service | Header injected |
|---|---|---|
| garmin | `garmin` | `X-Garmin-Token: <garth_tokens_json>` |
| google-workspace | `google` | `Authorization: Bearer <access_token>` |
| splitwise | `splitwise` | `X-Splitwise-Key: <api_key>` |
| journal-db | (none — operator secret) | (none — uses env DB_PASSWORD) |
| google-places | (none — operator API key) | (none — uses env) |

**MCP server side:** Each MCP server already reads credentials from env vars. For per-user headers, each server needs a small middleware that checks for the user header and overrides the env-sourced credential. This is a Phase 2+ concern — for now, the bridge injects headers, and MCP servers ignore them (operator creds still work for single user). The **point** is that the gateway-side plumbing is ready.

**`mcp_bridge.py` fix:** Pass `config.headers` to `streamablehttp_client()`:
```python
# Before:
streamablehttp_client(url=config.url)
# After:
streamablehttp_client(url=config.url, headers=config.headers or {})
```

**`web_server.py` refactor:**
- Replace `_mcp_bridge` global with `_bridge_manager: BridgeManager`
- `get_or_create_graph()` accepts `mcp_bridge` parameter (per-call override)
- `JournalGraph._get_config()` accepts `mcp_bridge` override
- WebSocket handler: extract `user_id` from auth → `bridge_manager.get_bridge(user_id)` → pass to graph
- HTTP chat handler: same pattern

**Files:** `bridge_manager.py` (new), `mcp_bridge.py` (header passthrough fix), `web_server.py` (refactor), `graph/graph.py` (per-call bridge override)

### ✅ 1.5d. BYOK — Bring Your Own (LLM) Key

Power users supply their own LLM API keys (main cost driver). Stored in `user_credentials` alongside service tokens.

**How it works:**
1. User stores their key: `CredentialStore.put(user_id, "llm_anthropic", {"api_key": "sk-ant-..."})`
2. At session start, `get_or_create_graph()` checks CredentialStore for user's LLM key
3. If found, creates LLMConfig with user's key
4. If **not** found, check whether this user has **operator key fallback** approved (see below)
5. If approved, use operator key from env. If not approved, reject the request (HTTP 403 — "No LLM key configured. Provide your own key or request operator access.")

**Operator key fallback is NOT automatic.** The operator (admin) must explicitly grant a user permission to use the shared operator LLM key. This prevents random users from racking up costs on the operator's API account.

**`api_keys` table extension — `allow_operator_llm` flag:**
```sql
ALTER TABLE api_keys ADD COLUMN allow_operator_llm BOOLEAN NOT NULL DEFAULT FALSE;
```

This flag is set by the admin via an admin console (Phase 2+ UI) or directly in the DB. When `TRUE`, the user's sessions can fall back to the operator's env-sourced LLM key. When `FALSE` (default for new users), the user **must** supply their own key via BYOK.

**Resolution order in `get_or_create_graph()`:**
1. Check `CredentialStore.get(user_id, "llm_anthropic")` (or `"llm_openai"`, based on provider)
2. If found → use user's key
3. If not found → check `api_keys.allow_operator_llm` for this user
4. If `allow_operator_llm = TRUE` → use operator key from env
5. If `allow_operator_llm = FALSE` → return 403

**For the current single-user case (varun):** The auto-seeded api_key row from 1.5a sets `allow_operator_llm = TRUE`, so existing behavior is preserved.

**user_credentials entries for BYOK:**

Users can store keys for both providers simultaneously. The right key is selected based on which provider the session is using — no conflict, both coexist.

| service | token_data | Used when |
|---|---|---|
| `llm_anthropic` | `{"api_key": "sk-ant-...", "preferred_model": "claude-sonnet-4-6"}` | Provider is `claude` (any Claude model) |
| `llm_openai` | `{"api_key": "sk-...", "preferred_model": "gpt-5-nano"}` | Provider is `openai` (any GPT model) |

Service names are fixed to the API company, not the model family, so adding new models (e.g. Claude Opus 5) requires no schema change.

**Metering:** Each thread already tracks `total_input_tokens` and `total_output_tokens`. With BYOK, the `model_provider` column distinguishes whose key was used. Usage stats endpoint already returns per-model breakdowns — no changes needed there.

**UI (future):** Settings page → "LLM Keys" → paste key → stores via CredentialStore. Admin console → toggle `allow_operator_llm` per user. No UI work in this phase.

**Files:** No new files — `credential_store.py` and `web_server.py` changes from 1.5b/1.5c cover this. The additions are: `allow_operator_llm` column on `api_keys`, and the BYOK resolution logic in `get_or_create_graph()`.

### Implementation order

```
1.5a  api_keys table + middleware      (no deps — start here)
1.5b  CredentialStore class            (needs PG pool from startup)
1.5c  BridgeManager + per-session      (needs CredentialStore)
1.5d  BYOK in get_or_create_graph      (needs CredentialStore)
```

All four steps can be done in one session. No external dependencies. No breaking changes to existing single-user flow (CredentialStore returns None → falls back to env vars).

---

## ✅ Phase 2: Infrastructure Agent Layer — COMPLETE (2026-02-22)

**Goal:** Multi-agent infrastructure live. COS, task agents, background agents, foreground agents all functional.

#### 2a. Skill router ✅

`skill_router` node in `graph/nodes.py` — slash commands, session persistence, journal intent fallback.

#### 2b. User context injection ✅

`user-context.md` + `daily-context.json` injected into every agent's system prompt.

#### 2c. `scheduler.py` + `notification_queue.py` ✅

- `scheduler.py`: `AgentScheduler` — asyncio background task, polls `scheduler` table every 60s, fires agents via `on_due_agent` callback (injected by AgentSpawner). Admin helpers: `schedule()`, `unschedule()`, `list_schedules()`.
- `notification_queue.py`: `NotificationQueue` + `ArtifactStore` — agents write artifacts (`write_artifact`), post notifications (`post`). Pushes to open WebSocket immediately; queues in DB for offline users. `get_unread()` / `mark_read()` for COS session start.

#### 2d. `agent_spawner.py` ✅

`AgentSpawner` with three agent types:
- `invoke_task(skill, task, context)` → ephemeral thread, returns text to caller (inline sub-tasks)
- `spawn_background(agent_name, skill, config)` → `asyncio.create_task`, writes artifact + notification on completion
- `spawn_foreground(skill, pre_task)` → persistent `ThreadManager` thread, optional pre-warm, returns `thread_id` for user switch

#### 2e. COS system prompt ✅

`~/.claude/skills/cos/SKILL.md` — COS as always-on orchestrator. Decision framework: answer directly / activate skill / spawn background / spawn foreground. Proactive intelligence, notification surfacing, communication style rules. Registered in `SKILL_MAP` and `SKILL_ALLOWED_SERVERS` (unrestricted — all servers).

---

## ✅ Phase 2.5: All-DB Agent System + System Agents — COMPLETE (2026-02-22)

**Goal:** Unified agent architecture. User agents fully DB-backed. System agents filesystem-backed, access-controlled. Admin role defined. Architect agent captures system knowledge.

### Agent categories

**User agents** (`agents/` seeding workspace → `agent_templates` + `agent_instances` DB):
- `agent_templates`: shared definitions seeded once during setup from `agents/` dir (not in Docker image)
- `agent_instances`: per-user rows with mutable SOUL, optional customizations per file
- Templates: `cos` (v2, always-active), `financial-advisor` (v2, dormant), `fitness-coach` (v2, dormant)
- COS can create new user-defined agents at runtime → inserted directly into `agent_instances`

**System agents** (`system-agents/` → ships in Docker image, no DB):
- Service-level: same for all users, no soul, no per-user instances
- Access-controlled via `access:` AGENT.md frontmatter: `cos_internal`, `admin_direct`
- `AgentLoader` resolution step 3: `system-agents/{name}/` → enforce access → load from filesystem
- Docs organized as indexed files in `docs/` subdirectory; BOOTSTRAP.md is the index

Current system agents: `architect` (codebase, schema, security, agent-system, deployment docs)

### Admin role

`api_keys.profile_name` as role field:
- `personal` → regular user, COS-only access
- `admin` → operator, can invoke system agents directly + manage api_keys
- `cos_internal` → internal COS trust level for system agent invocation

### Files
- `agent_loader.py` — `AgentLoader` (resolution chain + system-agents + access control), `AgentSeeder`, `AgentNotFoundError`, `AgentAccessDeniedError`
- `migrations/add_agent_system.sql` — `agent_templates` + `agent_instances` tables
- `migrations/run_add_agent_system.py` — runs DDL
- `migrations/run_seed_agent_templates.py` — seeds cos, financial-advisor, fitness-coach templates
- `agents/cos/` — COS AGENT.md v2 (name, persona integrity), TOOLS.md, HEARTBEAT.md, BOOTSTRAP.md
- `agents/financial-advisor/` — AGENT.md v2 (full advisory persona), TOOLS.md, HEARTBEAT.md, BOOTSTRAP.md
- `agents/fitness-coach/` — AGENT.md v2 (full coaching persona), TOOLS.md, HEARTBEAT.md, BOOTSTRAP.md
- `system-agents/architect/` — AGENT.md (access model), TOOLS.md, BOOTSTRAP.md (index), `docs/` (5 reference files)
- `.dockerignore` — `agents/` excluded (seeded), `system-agents/` included

---

## Files Created / Modified

| Phase | Path | Status |
|---|---|---|
| 1 | `journal-processor/agent-orchestrator/profile.py` | ✅ Created — `AssistantProfile` + `build_personal_profile()` |
| 1 | `journal-processor/agent-orchestrator/Dockerfile` | ✅ Created |
| 1 | `db-mcp-server/Dockerfile` | ✅ Updated (was outdated) |
| 1 | `google-workspace-mcp-server/Dockerfile` | ✅ Created |
| 1 | `garmin-mcp-server/Dockerfile` | ✅ Created |
| 1 | `googleplaces-mcp-server/Dockerfile` | ✅ Created |
| 1 | `splitwise-mcp-server/Dockerfile` | ✅ Created |
| 1 | `docker-compose.yml` | ✅ Created |
| 1 | `.env.production.example` | ✅ Created |
| 1 | `.gitignore` (root) | ✅ Created |
| 1 | `agent-orchestrator/.dockerignore` | ✅ Created |
| 1 | `agent-orchestrator/graph/graph.py` | ✅ Modified — `create_journal_graph_postgres()` + pool cleanup |
| 1 | `agent-orchestrator/graph/__init__.py` | ✅ Modified — exports new function |
| 1 | `agent-orchestrator/web_server.py` | ✅ Modified — Profile wiring, auth middleware, PG/SQLite fallback |
| 1 | `agent-orchestrator/skills.py` | ✅ Modified — `data_dir` in constructor, `gmail`→`google-workspace` |
| 1 | `agent-orchestrator/requirements.txt` | ✅ Modified — PG deps added |
| 1 | `agent-orchestrator/migrations/create_assistant_system.sql` | ✅ Created |
| 1 | `agent-orchestrator/migrations/run_create_assistant_system.py` | ✅ Created + run |
| 1 | `agent-orchestrator/migrations/migrate_threads_to_postgres.py` | ✅ Created + run (57 threads migrated) |
| 1 | `mcp-server-manager/servers.json` | ✅ Modified — inline creds removed |
| 1 | `mcp-server-manager/.gitignore` | ✅ Created |
| 1 | `db-mcp-server/.env.production` | ✅ Modified — `DB_NAME=varun_journal` |
| 1.5 | `agent-orchestrator/migrations/add_api_keys.sql` | ✅ Created — api_keys table DDL |
| 1.5 | `agent-orchestrator/migrations/run_add_api_keys.py` | ✅ Created + run — auto-seeds from ASSISTANT_API_KEY |
| 1.5 | `agent-orchestrator/credential_store.py` | ✅ Created — AES-256-GCM encrypt/decrypt, CRUD, lazy key rotation |
| 1.5 | `agent-orchestrator/bridge_manager.py` | ✅ Created — per-user MCPToolBridge cache, credential→header injection |
| 1.5 | `agent-orchestrator/web_server.py` | ✅ Modified — DB-backed auth, _auth_pool, _credential_store, _bridge_manager, BYOK resolution |
| 1.5 | `agent-orchestrator/mcp_bridge.py` | ✅ Modified — pass config.headers to streamablehttp_client |
| 1.5 | `agent-orchestrator/graph/graph.py` | ✅ Modified — per-call mcp_bridge override in _get_config, chat(), stream_chat() |
| 1.5 | `agent-orchestrator/requirements.txt` | ✅ Modified — added `cryptography>=43.0.0` |
| 1.5 | `agent-orchestrator/migrations/create_assistant_system.sql` | ✅ Modified — added api_keys table to master DDL |
| 1.5 | `.env.production.example` | ✅ Modified — added CREDENTIALS_ENCRYPTION_KEY |
| 2 | `agent-orchestrator/scheduler.py` | ✅ Created — AgentScheduler (cron polling, on_due_agent callback, admin helpers) |
| 2 | `agent-orchestrator/notification_queue.py` | ✅ Created — NotificationQueue + ArtifactStore (write/get/list artifacts, post/get_unread/mark_read notifications, WS push) |
| 2 | `agent-orchestrator/agent_spawner.py` | ✅ Created — AgentSpawner (invoke_task, spawn_background, spawn_foreground) |
| 2 | `~/.claude/skills/cos/SKILL.md` | ✅ Created — COS system prompt (orchestrator role, decision framework, proactive intelligence) |
| 2 | `agent-orchestrator/skills.py` | ✅ Modified — added `cos` to SKILL_MAP + SKILL_ALLOWED_SERVERS |
| 2 | `agent-orchestrator/requirements.txt` | ✅ Modified — added `croniter>=3.0.0` |
| 2 | `agent-orchestrator/web_server.py` | ✅ Modified — _notification_queue, _scheduler, _spawner globals; startup init; shutdown stop; WS register/unregister + pending notification delivery; REST endpoints (scheduler, notifications, artifacts) |

---

## Risks

| Risk | Mitigation |
|---|---|
| Google OAuth expires headless on VM | Persistent volume + auto-refresh + alert if fails |
| Garmin session expires | Persistent volume + alert + re-auth flow |
| LLM API cost | Context distillation built; token budgets per session |
| VM is SPOF | Azure auto-restart + Docker restart policies |

## Cost Estimate

| Component | Monthly |
|---|---|
| Azure VM B2s (all containers) | ~$30 |
| Azure PostgreSQL (varun_journal + assistant_system) | ~$15-25 |
| LLM API (Sonnet + Haiku distillation) | ~$20-50 |
| **Total** | **~$65-105/month** |
