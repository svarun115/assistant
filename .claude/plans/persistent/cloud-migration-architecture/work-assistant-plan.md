# Work Assistant Plan

**Depends on:** [infra-architecture.md](infra-architecture.md) — infrastructure must be complete first.
**Status:** Stub — to be planned in a dedicated session when personal assistant is stable.

---

## Work Profile (stub)

```python
work_profile = AssistantProfile(
    name="work",
    mcp_servers=[
        # Agency CLI MCP servers (internal Microsoft tooling)
        MCPServerConfig("kusto",   ...),   # agency mcp kusto --service-uri <cluster>
        MCPServerConfig("ado",     ...),   # agency mcp ado
        MCPServerConfig("icm",     ...),   # agency mcp icm
        MCPServerConfig("bluebird",...),   # agency mcp bluebird
        # Work email via Google Workspace or Outlook (TBD)
    ],
    journal_db_url="postgresql://...@.../work_journal",   # separate from personal
    system_db_url="postgresql://...@.../assistant_system",  # shared infra
    skills_dir=Path("~/.claude/skills/work"),
    allowed_skills=["kusto", "create-ado", "pr-feedback-analyzer", "pr-reviewer", "ado-context-gatherer"],
    llm_config=LLMConfig(provider=CLAUDE, model="claude-sonnet-4-6"),
)
```

---

## Work Skills (to port from `~/.claude/skills/work/`)

| Skill | Purpose |
|---|---|
| `/kusto` | KQL analysis against Azure Data Explorer clusters |
| `/create-ado` | Create Azure DevOps work items (bugs, tasks, user stories) |
| `/pr-feedback-analyzer` | Analyze PR review comments, triage feedback |
| `/pr-reviewer` | Review PRs assigned to me, analyze changes |
| `/ado-context-gatherer` | Gather full context for ADO work items |

---

## Work MCP Servers

All via the Agency CLI (`agency mcp <name> [options]`):

| Server | Agency command | Tools |
|---|---|---|
| Kusto | `agency mcp kusto --service-uri <cluster>` | KQL query, list databases |
| ADO | `agency mcp ado` | Work items, PRs, repos |
| ICM | `agency mcp icm` | Incident management |
| Bluebird | `agency mcp bluebird` | Microsoft internal |

---

## Work Agents (to be designed)

| Agent | Type | Example |
|---|---|---|
| PR review | Foreground (pre-warmed) | Fetches + prioritizes PRs at 2:55pm; user switches at 3pm |
| Standup prep | Background (scheduled) | Pulls yesterday's ADO activity + PRs at 9:45am; ready at 10am standup |
| Work email triage | Background (scheduled) | Processes work inbox separately from personal |
| Incident response | Foreground (on-demand) | COS spawns when ICM alert comes in |
| Experiment analysis | Foreground (on-demand) | Kusto queries + analysis for a specific experiment |

---

## Cross-COS: Personal ↔ Work Coordination

Both COS instances need to coordinate without leaking data. See cross-COS federation design in [infra-architecture.md](infra-architecture.md).

**Personal → Work:** "I have a gym session at 7am and family dinner at 7pm. Block morning and evening."
**Work → Personal:** "You have a major incident on-call rotation this week. Flag as high-stress week."

Trust level between own profiles: `FULL_COLLABORATION` — near-full context sharing since it's the same person.

---

## Work Journal DB

Separate from `varun_journal`. Will contain:
- Work events (meetings, code reviews, incidents)
- Work journal entries (notes, decisions)
- Work daily plans
- No personal health, finance, or family data

Name TBD: `work_journal` or `varun_work_journal`.

---

## Notes for Planning Session

When ready to plan the work assistant:
1. Audit existing Claude Code work skills — what's working, what needs updating
2. Decide: same Azure PostgreSQL server or separate (MSFT data classification concerns)?
3. Agency CLI MCP server configuration for each tool
4. Work COS system prompt — different personality/context than personal COS
5. Cross-COS trust configuration between personal and work profiles
6. Work schedule: standup prep timing, PR review windows, incident on-call setup
