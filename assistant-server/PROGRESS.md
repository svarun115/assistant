# Journal Agent Orchestrator — Progress Tracker

> **Last Updated:** 2026-01-01

## Implementation Status

### Core Components

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| MCP Tool Bridge | `mcp_bridge.py` | ✅ Done | Streamable HTTP, pre-connectivity check, async context manager |
| LLM Clients | `llm_clients.py` | ✅ Done | Claude, OpenAI, Ollama support |
| Configuration | `config.py` | ✅ Done | Server configs, LLM settings |
| Conversation Manager | `conversation.py` | ✅ Done | Basic state, needs distillation |
| Skills Loader | `skills.py` | ✅ Done | Reads from docs/domain-instructions/ |
| Timeline Skeleton | `skeleton.py` | ✅ Done | Multi-source synthesis, gap detection |
| Agent Core | `agent.py` | ✅ Done | Agentic loop, tool calling |

### Interfaces

| Interface | File | Status | Notes |
|-----------|------|--------|-------|
| CLI | `cli.py` | ✅ Done | Basic chat, /history, UTF-8 fix |
| Web Server | `web_server.py` | ✅ Done | FastAPI + WebSocket |
| Web UI | `static/` | 🔄 In Progress | See UI Features below |

### Web UI Features

| Feature | Status | Notes |
|---------|--------|-------|
| Chat interface | ✅ Done | Full-screen, markdown rendering |
| Model selector | ✅ Done | Claude, ChatGPT, Gemini |
| Dev Pane (left) | ✅ Done | Session, Tool Usage, Tokens, Conversation tiles |
| MCP Servers view | ✅ Done | Navigable from Dev Pane, shows servers/tools |
| Tool detail view | ✅ Done | Click tool to see description, params, server |
| Timeline pane (right) | ✅ Done | Always-visible, date selector (350px) |
| Theme toggle | ✅ Done | Light/dark mode with localStorage |
| Settings dropdown | ✅ Done | Display mode (conversation/full) |
| User-friendly errors | ✅ Done | Error message mapping |
| Tool usage tracking | ✅ Done | Count per tool in session |
| Token usage tracking | ✅ Done | Backend sends usage in WebSocket response |
| Auto-detect date | ✅ Done | Backend detects, sends detected_date |
| Timeline auto-fetch | ✅ Done | Frontend calls setTimelineDate() on detection |

### Backend Features

| Feature | Status | Notes |
|---------|--------|-------|
| REST API | ✅ Done | /chat, /tools, /tool/{server}/{name}, /models, /timeline |
| WebSocket streaming | ✅ Done | Real-time responses |
| Timeline API | ✅ Done | Query events by date range |
| Tool detail API | ✅ Done | Get full tool schema |
| Token tracking | ✅ Done | LangGraph tracks total_input_tokens, total_output_tokens per thread |
| Cost estimation | ✅ Done | UsageRecord includes cost_usd field |
| Date detection | ✅ Done | `_detect_date()` in nodes.py parses "yesterday", "Dec 31", etc. |

---

## Known Issues

| Issue | Severity | Notes |
|-------|----------|-------|
| Gmail auth expired | Medium | `invalid_grant` error, needs re-auth |
| MCP disconnect warnings | Low | Cancel scope errors on shutdown |
| Tool name mismatch | Low | `mcp_personal_jour_*` vs `*` naming |

---

## Next Steps (Priority Order)

1. **Token tracking backend** — Track input/output tokens per API call, send to frontend
2. **Date detection** — Parse "yesterday", "Dec 31", etc. from user messages
3. **Timeline auto-fetch** — When date detected, populate Timeline tab
4. **Conversation distillation** — Summarize older turns to save context
5. **Error recovery** — Retry failed MCP connections

---

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Streamable HTTP over stdio | Better for remote/containerized MCP servers |
| Pre-connectivity check | Fail fast if server unreachable |
| Frontend token tracking | Simpler than backend state, resets on refresh |
| Separate Timeline + Debug panels | Timeline always visible for context; Debug collapsible for dev use |
| Skills in orchestrator | Domain knowledge stays in agent, MCP servers are dumb pipes |

---

## Session Log

### 2026-01-01
- Created web interface with FastAPI + vanilla JS
- Redesigned right sidebar: Timeline pane (always visible, 350px) + Debug panel (collapsible, 280px)
- Simplified model selector to 3 options
- Added theme toggle (light/dark)
- Added tool usage and token cost tracking (frontend)
- Fixed MCP bridge async context manager
- Added /api/timeline endpoint
- Updated copilot-instructions.md for development context
- Moved skills from `.claude/skills/` to `docs/domain-instructions/`
