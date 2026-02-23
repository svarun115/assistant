# Personal Assistant — Master Plan

## Executive Summary

**What this is:** A self-hosted personal AI assistant with an always-on Chief of Staff (COS), specialist agents (financial advisor, fitness coach), and a background agent pipeline for autonomous work. Built on FastAPI + LangGraph + PostgreSQL + Docker.

**Current status (2026-02-23):**

| Layer | Status |
|---|---|
| Core infrastructure (auth, multi-user, DB, Docker) | ✅ Complete |
| Agent system (templates, instances, soul, heartbeat, scheduler) | ✅ Complete |
| COS + specialist agent definitions (cos, financial-advisor, fitness-coach) | ✅ Complete |
| System Architect with indexed reference docs | ✅ Complete |
| Background agent pipeline (scheduler → artifact → notification) | ✅ Complete |
| MCP server cloud deployment artifacts (docker-compose, nginx, deploy.sh, client config) | ✅ Complete |
| MCP servers on Azure VM (machine-independent Claude Code access) | ⏳ Not started |
| Assistant-server/gateway on Azure VM | ⏳ Deferred — not current priority |
| Web UI (bootstrap flow, daily plan, mobile) | ⏳ Not started |
| First user registered and using the system | ⏳ Blocked on gateway VM |

**Current priority:** Deploy MCP servers to Azure VM → update `~/.claude.json` on any machine → Claude Code works anywhere, no laptop dependency.

**Immediate next step:** Provision Azure B2s VM → `./deploy.sh setup-docker` → `./deploy.sh deploy` → `./deploy.sh setup-nginx YOUR-DOMAIN` → update `~/.claude.json` using `mcp-servers.cloud.example.json`.

---

## Part 1 — System Development

Everything needed to stand up a working, production-ready instance.

### ✅ Done

**Infrastructure**
- `varun_journal` (personal data DB) + `assistant_system` (infra state DB, all tables, RLS)
- LangGraph checkpoints in PostgreSQL (`assistant_system`)
- Docker Compose: 6 containers (assistant gateway + 5 MCP servers)
- `AssistantProfile` — all config from env vars, no hardcoded values

**Auth + Multi-user foundation**
- `api_keys` table: SHA-256 hashed keys → `user_id` + `profile_name` (roles: personal, admin, cos_internal)
- `CredentialStore`: AES-256-GCM encryption, `user_credentials` table
- `BridgeManager`: per-user `MCPToolBridge` with credentials injected as HTTP headers
- BYOK: users supply own Anthropic/OpenAI keys; operator key requires explicit `allow_operator_llm=TRUE`

**Agent system**
- `agent_templates` + `agent_instances` tables (all-DB, per-user soul, customizable)
- `AgentLoader`: 3-step resolution (instances → templates → system-agents/)
- `AgentSeeder`: one-time setup seeding from `agents/` directory
- System agents (`system-agents/`): filesystem-backed, service-level, access-controlled
- Agent templates seeded: `cos` v2, `financial-advisor` v2, `fitness-coach` v2
- System agent: `Architect` (full system knowledge, indexed docs, cos_internal + admin_direct access)

**Agent runtime**
- `AgentSpawner`: task agents (ephemeral), background agents (fire-and-forget), foreground agents (persistent threads)
- `AgentScheduler`: 60s polling, heartbeat-driven schedule sync
- `NotificationQueue` + `ArtifactStore`: agent → COS delivery, WebSocket push
- Schedules seeded: daily-planner, email-triage, retro, expenses-reminder, fitness-coach-weekly, financial-advisor-weekly

**COS agent definition**
- `cos/AGENT.md`: orchestrator role, persona integrity guardrail, custom name support, decision framework
- `cos/HEARTBEAT.md`: owns its own schedules (daily-planner, email-triage, retro, expenses-reminder)
- `cos/BOOTSTRAP.md`: session init logic, first-session detection for guided setup

---

### ⏳ Remaining

#### 1g — Azure VM Deployment
Provision the VM, install Docker, configure Nginx + Let's Encrypt, deploy.

```
VM spec:    Azure B2s (~$30/month): 2 vCPUs, 4GB
Steps:      Clone repo → .env.production → copy OAuth tokens →
            docker-compose up -d → verify all containers healthy
Access:     HTTPS via Nginx reverse proxy → Let's Encrypt TLS → port 8080
```

This is the gate. Nothing in Part 2 is possible until this is done.

---

#### Phase 3 — Web UI

##### 3a. Bootstrap / Setup Flow
First-session COS experience. COS guides the user through setup in conversation:

1. Intro: "I'm COS, your Chief of Staff. Let's get you set up. Would you like to give me a name?"
2. Activate dormant agents: explain financial-advisor and fitness-coach, offer to activate
3. For each activated agent: COS interviews the user → context seeded into `soul_md` → heartbeat schedules synced
4. Confirm daily schedule (show defaults, let user adjust times/days)
5. COS ready to use

**Technically:** `agent_loader.create()` + `scheduler.sync_from_heartbeats()` called when user activates an agent. COS soul updated with user preferences. All tracked in `agent_instances`.

##### 3b. Daily plan panel
Not buried in chat — dedicated panel always visible.

```
┌────────────────┬───────────────────────────────┐
│  TODAY'S PLAN  │                               │
│  ─────────     │   COS chat                    │
│  8:00 Run      │                               │
│  ✓ 9:00 Standup│                               │
│  → 10:00 Focus │   [Active Agents]             │
│  12:30 Lunch   │   Financial Review  ● Ready   │
│                │   Email Triage  ✓ Done         │
│  Plan vs Actual│                               │
│  ████████░░ 80%│                               │
└────────────────┴───────────────────────────────┘
```

Data: `get_plan_vs_actual`, `create_daily_plan` from journal MCP.

##### 3c. Foreground agent switcher
Thread list becomes the agent switcher:
- COS — always pinned at top, notification badge if unread
- Active foreground agents — status (pre-loading / ready / in-progress)
- Past conversation threads — scrollable history

##### 3d. Mobile-responsive + PWA
- Mobile `<768px`: plan panel accessible via tab
- `manifest.json` + service worker → "Add to Home Screen" on iPhone Safari

##### 3e. Agent management UI
- View installed agents, their soul (read-only summary), active schedules
- Export agent as zip / import from zip or URL
- Admin view: manage api_keys, view all user instances

---

## Part 2 — Registration & Bootstrapping (v1 Go-Live)

**Goal:** The system is deployed and Varun is fully set up as the first user.

This is not a build phase — it's a series of one-time actions after the Web UI is live.

### Steps

**1. Deploy (Phase 1g)**
VM running, HTTPS accessible, all containers healthy.

**2. Run setup migrations** (one-time, already scripted)
```bash
python migrations/run_create_assistant_system.py
python migrations/run_add_api_keys.py
python migrations/run_add_agent_system.py
python migrations/run_seed_agent_templates.py   # seeds cos, financial-advisor, fitness-coach
python migrations/seed_schedules.py             # COS-level schedules
```

**3. Import existing skills**
The existing `~/.claude/skills/` files (financial-advisor with investment context, fitness-coach with training notes) can be imported into the agent system via:
- `POST /api/agents/import` (once the import endpoint is built in Phase 3e)
- Or manually seeded into `agent_instances` for Varun as a one-time operation

**4. Open COS for first time**
- COS detects empty soul → runs guided setup flow (Phase 3a)
- Varun provides context for financial-advisor and fitness-coach during setup
- COS creates the agent instances with soul pre-loaded
- Schedules go live automatically

**5. Verify the pipeline**
- Background agent fires (e.g. email-triage at 9am)
- Artifact written to `artifacts` table
- Notification delivered to COS WebSocket
- COS surfaces it at session start

**6. Done** — Varun is using v1.

---

## Part 3 — Future

Ordered roughly by value / effort ratio. None of these are planned in detail yet.

### Near-term (high value, low effort)
- **Work assistant** — separate profile, work skills (Kusto, ADO, PR review). All infra ready; just needs a `work_journal` DB and work agent definitions. (See `work-assistant-plan.md` stub.)
- **Admin console** — simple web UI for managing api_keys, viewing agent instances, triggering template upgrades

### Medium-term
- **Telegram integration** (~1 session) — `python-telegram-bot` webhook → gateway `/api/chat`. More important as notification channel than chat interface.
- **Agent import/export** — `GET /api/agents/{name}/export` (zip), `POST /api/agents/import` (zip/URL). Enables sharing and portability.

### Long-term
- **iPhone sensor layer** (~3-4 sessions) — HealthKit sync (sleep, workouts → journal), LocationServices (home/work/gym detection), CallKit (call logs), APNs push notifications
- **Voice** — Whisper (speech→text) + TTS (text→speech)
- **Cross-COS federation** — personal ↔ work COS coordination (`cos_trust_registry` table already exists)
- **Architect capabilities** — Architect can propose and create DB schema extensions, trigger migrations, configure new agent types based on user needs. Each user can have a unique schema.
- **Multi-user** — second user onboarding via the same bootstrap flow. All infrastructure is ready (`user_id` isolation is complete); just needs a new api_key row.

---

## Reference

Detailed technical specs are in `infra-architecture.md` (phases 0–2.5 with implementation notes).
`work-assistant-plan.md` is a stub pending personal assistant stability.
