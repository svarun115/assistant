# Plan: Agent SDK Journal Logging Service

**Created:** 2026-02-10
**Status:** Draft — research + design phase
**Goal:** Replace per-invocation quick-log subagent spawning with a persistent logging service built on the Claude Agent SDK, enabling warm-context logging across the entire session (and potentially across sessions).

---

## Problem Statement

The current quick-log architecture spawns a fresh Task agent for each logging batch. Even with the `resume` optimization (implemented 2026-02-10), the system is constrained by Claude Code's task-oriented lifecycle:

1. **No MCP tools in background agents** — quick-log can't use journal MCP when running in background; it must run foreground or work around this
2. **Resume is session-scoped** — agent IDs don't survive across Claude Code sessions
3. **Each resume is still an API round-trip** — context is preserved but still requires a new API call per batch
4. **No concurrent access** — can't have the logging service processing one batch while the user continues chatting

The Agent SDK removes all these constraints by running the agent as a standalone process.

---

## Target Architecture

```
┌─────────────────────────────────┐
│  Claude Code (daily-tracker)    │
│                                 │
│  User: "I had lunch then gym"   │
│           │                     │
│           ▼                     │
│  MCP call: log_events(...)  ────┼──► HTTP/stdio ──┐
│  (non-blocking)                 │                  │
│           │                     │                  ▼
│  Acknowledge immediately        │    ┌─────────────────────────┐
│  "Logging lunch and gym..."     │    │  Journal Logging Service │
│                                 │    │  (Agent SDK process)     │
└─────────────────────────────────┘    │                         │
                                       │  - Persistent session    │
                                       │  - Warm entity context   │
                                       │  - Full MCP access       │
                                       │  - Journal skill loaded  │
                                       │           │              │
                                       │           ▼              │
                                       │  MCP: personal-journal   │
                                       │  (create_event, etc.)    │
                                       └─────────────────────────┘
```

### Communication Model

Two options for Claude Code ↔ Logging Service communication:

**Option A: Custom MCP Server (preferred)**
- The logging service exposes itself as an MCP server (stdio or HTTP)
- Claude Code calls it like any other MCP tool: `mcp__journal-logger__log_events(...)`
- Seamless integration — no HTTP wiring needed in the skill
- Daily-tracker skill just calls the MCP tool directly

**Option B: HTTP API**
- Logging service runs as a local HTTP server (e.g., `localhost:8321`)
- Daily-tracker spawns a Bash `curl` call to submit events
- More decoupled but more plumbing to set up

---

## Implementation Phases

### Phase 1: Research & Prototype (1-2 sessions)

**Goal:** Validate the Agent SDK can do what we need.

- [ ] Install Agent SDK: `pip install claude-agent-sdk` or `npm install @anthropic-ai/claude-agent-sdk`
- [ ] Build minimal prototype:
  ```python
  # Validate: can we create a persistent session that uses journal MCP?
  async for msg in query(
      prompt="Log a test event: 'Test entry' at 2026-02-10T12:00:00",
      options=ClaudeAgentOptions(
          mcp_servers={"journal": {"command": "...", "args": [...]}},
          allowed_tools=["mcp__journal__*"]
      )
  ):
      if msg.subtype == "init":
          session_id = msg.session_id  # Can we resume this?
  ```
- [ ] Validate session resumption preserves MCP tool access
- [ ] Validate the agent can read/write `daily-context.json` via the SDK's file tools
- [ ] Measure latency: first call vs resumed call

**Key questions to answer:**
1. Can the SDK agent connect to the same journal MCP server that Claude Code uses? Or does it need its own instance?
2. What's the session ID lifecycle — does it survive process restarts?
3. Can we run the SDK agent as a background process from Claude Code's hooks (e.g., `SessionStart` hook)?

### Phase 2: Build the Logging Service (2-3 sessions)

**Goal:** Production-quality logging service with MCP interface.

#### 2a. Core Service

- [ ] Create `~/.claude/services/journal-logger/` directory
- [ ] Build the service entry point (`server.py` or `server.ts`)
- [ ] Implement session management:
  - Start new session on first call of the day
  - Resume session for subsequent calls
  - Invalidate session at midnight or on explicit reset
- [ ] Load journal-agent.md + errata as system prompt on session start
- [ ] Connect to journal MCP server for DB operations
- [ ] Implement `log_events` endpoint:
  - Input: `{events: [...], entry_date: "YYYY-MM-DD", cache_path: "..."}`
  - Output: `{status: "success"|"partial"|"escalate", results: [...]}`

#### 2b. MCP Interface

- [ ] Expose the service as an MCP server using `createSdkMcpServer()` or equivalent
- [ ] Define tools:
  - `log_events` — batch log events (main tool)
  - `get_status` — check if service is running, session age
  - `reset_session` — force new session (e.g., after location change)
- [ ] Register with Claude Code: `claude mcp add --transport stdio journal-logger -- python ~/.claude/services/journal-logger/server.py`

#### 2c. Cache Integration

- [ ] Read `daily-context.json` on every invocation (same as current behavior)
- [ ] Write back resolved entities after processing
- [ ] Handle concurrent cache access (read-modify-write with basic conflict detection)

### Phase 3: Integrate with Daily Tracker (1 session)

**Goal:** Daily tracker calls the service instead of spawning agents.

- [ ] Update `daily-tracker/skill.md`:
  - Replace the "Journal Integration" section
  - Remove agent spawn logic
  - Add MCP tool call: `mcp__journal-logger__log_events(...)`
  - Keep escalation handling (service returns escalation results)
- [ ] Update `journal-agent.md`:
  - Add note that this file is now used as the system prompt for the logging service
  - No behavioral changes needed — the agent's logic stays the same
- [ ] Remove `journal_agent_id` / `journal_agent_date` from cache (no longer needed)
- [ ] Test: full day simulation with multiple check-ins

### Phase 4: Auto-Start & Lifecycle (1 session)

**Goal:** Service starts automatically and manages its own lifecycle.

- [ ] Add `SessionStart` hook in Claude Code to start the logging service if not running
- [ ] Implement health check endpoint
- [ ] Add graceful shutdown on Claude Code exit
- [ ] Handle service crash/restart:
  - Service detects stale session on restart
  - Creates new session, re-loads context
  - Logs a warning about the restart

---

## File Structure

```
~/.claude/services/journal-logger/
├── server.py              # Main service entry point
├── requirements.txt       # claude-agent-sdk, etc.
├── config.json            # MCP server configs, cache paths
├── README.md              # Setup & usage
└── tests/
    ├── test_logging.py    # Unit tests
    └── test_session.py    # Session persistence tests
```

---

## Open Questions

1. **SDK availability on Windows** — Does the Agent SDK run well on Windows? Or should this be a WSL-based service?
2. **API key management** — The SDK needs an Anthropic API key. How to manage this securely? Environment variable? Keychain?
3. **Cost model** — Each SDK call costs API tokens. Is the session resumption approach cheaper than spawning fresh agents in Claude Code? Need to benchmark.
4. **Journal MCP server** — Can two processes (Claude Code + logging service) connect to the same MCP server simultaneously, or do they need separate instances?
5. **Offline/error handling** — What happens if the service is down when the daily tracker tries to log? Fallback to inline logging? Queue events?

---

## Success Criteria

- [ ] Logging latency: < 3s for a batch of 3 events on resumed session (vs ~15-20s today for fresh agent)
- [ ] Zero dropped events: every user-reported activity gets logged
- [ ] Cache consistency: service and Claude Code don't clobber each other's cache updates
- [ ] Transparent to user: same daily-tracker UX, just faster acknowledgments
- [ ] Cost-neutral or cheaper: total API token usage should not increase

---

## Dependencies

- Claude Agent SDK (Python or TypeScript)
- Anthropic API key with sufficient quota
- Journal MCP server running locally
- `daily-context.json` cache (existing)
- `journal-agent.md` + errata (existing, used as system prompt)

---

## Related Files

- `~/.claude/skills/daily-tracker/skill.md` — Daily tracker skill (caller)
- `~/.claude/agents/journal-agent.md` — Quick-log agent prompt (becomes service system prompt)
- `~/.claude/agents/journal-agent-errata.md` — Errata rules
- `~/.claude/data/daily-context.json` — Daily context cache
- `~/.claude/skills/journal/entities.md` — Entity resolution rules
- `~/.claude/skills/journal/db-tool-cheatsheet.md` — DB tool reference
