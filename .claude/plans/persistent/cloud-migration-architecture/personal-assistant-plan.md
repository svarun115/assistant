# Personal Assistant Plan

**Depends on:** [infra-architecture.md](infra-architecture.md) — infrastructure must be complete first.
**Master plan:** See [README.md](README.md) for executive summary and overall status.

---

## Personal Profile

The personal profile is configured via env vars in `.env.production`. No code changes needed.

| Config | Value |
|---|---|
| MCP servers | journal-mcp, garmin, google-workspace, google-places, splitwise |
| Personal data DB | `varun_journal` |
| Infra state DB | `assistant_system` |
| Skills | journal, daily-tracker, email-triage, expenses (task skills via `~/.claude/skills/`) |
| Role agents | financial-advisor, fitness-coach (dormant templates; activated via bootstrap) |
| Default LLM | claude-sonnet-4-6 |

---

## Skill and Agent Model

### Task skills (stateless, `~/.claude/skills/`)
Invoked inline by COS or directly by the user. No soul. No persistent thread needed.

| Skill | Trigger | What it does |
|---|---|---|
| `/journal` | COS delegates, or user direct | LOG / REFLECT / QUERY modes |
| `/daily-tracker` | COS delegates or user direct | Planning, check-ins, wrap-up |
| `/email-triage` | Background scheduler (9am) + user-invocable | Inbox triage → `email_digest` artifact |
| `/expenses` | User-invoked (1st of month reminder) | UPI/bank PDF → Splitwise + Google Sheets |

**Retired Claude Code workarounds (not ported):**
- `/done` → COS handles wrap-up natively ("wrap this up" or end-of-session)
- `/retro` → Background retro agent runs at 9:30pm daily via scheduler

### Role agents (DB-backed instances, with soul)
Foreground sessions with persistent memory. Activated during bootstrap.

| Agent | Type | Trigger | Pre-warm on spawn |
|---|---|---|---|
| `financial-advisor` | Foreground | User → COS | Load portfolio from Sheets + soul (past decisions) |
| `fitness-coach` | Foreground | User → COS | Pull 14 days Garmin + active health conditions + soul |

### Background agents (scheduler-driven)
All declared in agent HEARTBEAT.md. Run autonomously, produce artifacts, notify COS.

| Agent | Schedule (IST) | Artifact | Declared in |
|---|---|---|---|
| daily-planner | 7:30 AM daily | `daily_plan` | `cos/HEARTBEAT.md` |
| email-triage | 9:00 AM daily | `email_digest` | `cos/HEARTBEAT.md` |
| retro | 9:30 PM daily | `retro` | `cos/HEARTBEAT.md` |
| expenses-reminder | 1st of month 9:30am | `expense_reminder` | `cos/HEARTBEAT.md` |
| fitness-coach-weekly | Mon 8:00 AM | `fitness_weekly` | `fitness-coach/HEARTBEAT.md` |
| financial-advisor-weekly | Sun 7:30 PM | `portfolio_weekly` | `financial-advisor/HEARTBEAT.md` |

All 6 are seeded into `assistant_system.scheduler`. The fitness/financial ones activate when the user's agent instances are created during bootstrap.

---

## Phase 3: Web UI + Bootstrap (~2 sessions)

**Goal:** Working UI accessible on all devices, with a guided first-session setup that activates the personal assistant for Varun.

### 3a. Bootstrap / Setup Flow *(prerequisite for everything else)*

COS detects first session (empty soul) and guides setup as a conversation:

1. **Intro**: "I'm COS, your Chief of Staff. Let's get you set up. Would you like to give me a name, or COS is fine?"
2. **Activate financial-advisor**: "I have a financial advisor agent available. Want to activate it? I'll need to know about your portfolio and goals to get started."
   - User provides context → COS creates `agent_instances` row with context pre-loaded into `soul_md`
   - Heartbeat schedules sync automatically (Sunday portfolio check goes live)
3. **Activate fitness-coach**: "I also have a fitness coach — it connects to your Garmin data. Want to set that up?"
   - User provides goals, current training, any injuries → `soul_md` seeded
   - Monday weekly recap goes live
4. **Import existing skills** (optional): "I see you have existing skill configurations from Claude Code. Want me to import your financial-advisor and fitness-coach context into the new agents?"
   - `POST /api/agents/import` or manual soul seeding
5. **Daily schedule**: Show default schedule, let user adjust times
6. **Done**: COS is live with full context. First background agents fire at their scheduled times.

**Technical implementation:**
- `agent_loader.create()` for user-defined extensions
- `agent_loader.update_file("financial-advisor", user_id, "soul_md", context)` for soul seeding
- `scheduler.sync_from_heartbeats(loader, user_id)` after each agent activation

### 3b. Daily Plan Panel

Dedicated panel always visible, not buried in chat.

```
┌────────────────────┬───────────────────────────────┐
│  [≡ Plan] [Chat] [Agents]      [⚙ Settings]        │
├────────────────────┼───────────────────────────────┤
│  TODAY'S PLAN      │                               │
│  ────────────      │  COS chat                     │
│  8:00 Run          │                               │
│  ✓ 9:00 Standup    │                               │
│  → 10:00 Focus     │  [Active Agents]              │
│  12:30 Lunch       │  Financial Review  ● Ready    │
│                    │  Email Triage  ✓ Done          │
│  Plan vs Actual    │                               │
│  ████████░░  80%   │                               │
└────────────────────┴───────────────────────────────┘
```

Data: `get_plan_vs_actual`, `create_daily_plan`, `update_plan_item` via journal MCP.
WebSocket push when plan updates.

### 3c. Foreground Agent Switcher

Thread list repurposed as agent switcher:
- **COS** — always pinned at top, unread notification badge
- **Active foreground agents** — status chip (pre-loading / ready / in-progress)
- **Past threads** — scrollable history below

### 3d. Mobile-responsive + PWA

```
Mobile <768px:   plan panel accessible via [≡ Plan] tab
Tablet 768-1024: side-by-side plan + chat
Desktop >1024:   full 3-column layout
```

`manifest.json` + service worker → "Add to Home Screen" on iPhone Safari.
Standalone window, offline shell for instant load.

### 3e. Agent Management UI

- View installed agents: soul summary (read-only), active schedules, last run
- Export agent as zip / import from zip or URL (`GET /api/agents/{name}/export`, `POST /api/agents/import`)
- Admin view: manage api_keys, view all user instances, trigger template upgrades

---

## Verification Checklist

After bootstrap:
- [ ] COS first session detects empty soul → runs guided setup
- [ ] financial-advisor and fitness-coach instances created with soul pre-loaded
- [ ] Background agents fire at scheduled times (check `artifacts` table + notifications)
- [ ] COS surfaces notification at next session start: "Your email digest is ready..."
- [ ] Foreground agent spawn: "Let's review my portfolio" → spawn_foreground → pre-warmed thread
- [ ] Open on iPhone Safari → responsive layout, plan panel visible, PWA installable

---

## Personal Agent Catalog (complete)

| Agent | Type | Trigger | Tool access | Output |
|---|---|---|---|---|
| COS | Always-on | User direct | All servers | Orchestration |
| journal | Task skill | COS or user | journal-db, garmin, google-places | Entry in varun_journal |
| daily-tracker | Task skill | COS or user | journal-db, garmin, google-workspace | Plans, check-ins |
| email-triage | Background + task | 9am scheduler / user | google-workspace, journal-db | email_digest artifact |
| expenses | Task skill | Monthly reminder / user | splitwise, google-workspace, journal-db | Splitwise + Sheets updated |
| financial-advisor | Foreground | User → COS | journal-db, google-workspace | Portfolio review, decisions |
| fitness-coach | Foreground | User → COS | garmin, journal-db | Training plan, recovery |
| financial-advisor-weekly | Background | Sun 7:30pm | google-workspace | portfolio_weekly artifact |
| fitness-coach-weekly | Background | Mon 8am | garmin, journal-db | fitness_weekly artifact |
| retro | Background | 9:30pm daily | journal-db | retro artifact |
| daily-planner | Background | 7:30am daily | journal-db, garmin, google-workspace | daily_plan artifact |
