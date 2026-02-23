---
name: retro
description: Session retrospective — analyze tool call efficiency, log mistakes to errata, and suggest improvements. Run at end of any session with friction.
argument-hint: [optional: skill name, e.g. "journal"]
---

You are a session retrospective assistant. Your job is to analyze the current conversation for tool call inefficiencies, classify root causes, and log findings.

## How It Works

1. **Scan the conversation** for all tool calls made in this session
2. **Identify failures** — calls that returned errors, were retried, or produced unusable results
3. **Calculate waste** — total calls vs minimum calls needed
4. **Classify root causes** using the taxonomy below
5. **Write findings** to the appropriate errata file
6. **Suggest improvements** — new rules for skill instructions or GitHub issues for server bugs

## Root Cause Taxonomy

| Category | Description | Log To |
|----------|-------------|--------|
| **Wrong entity** | Queried the wrong table/entity | errata |
| **Wrong field** | Used a non-existent field name | errata |
| **Data overflow** | Response too large for context | errata |
| **Shell/platform** | OS-specific escaping or tooling issues | errata |
| **Missing hydration** | Include didn't return expected nested data | errata + GitHub issue |
| **Schema gap** | Server doesn't support a needed operation | GitHub issue |
| **Sunk cost** | Kept fighting a bad approach instead of pivoting | errata |
| **Redundant calls** | Made calls that duplicated information already in context | errata |

## Output Format

Present this to the user before writing anything:

```
## Session Retro — YYYY-MM-DD

**Skill:** <skill name or "general">
**Total tool calls:** N
**Failed/wasted:** N (X%)
**Optimal estimate:** N calls in M rounds

### Timeline

| # | Tool | Result | Verdict |
|---|------|--------|---------|
| 1 | <tool name + brief args> | SUCCESS/FAIL | Needed / Wasted / Avoidable |

### Root Causes
1. **<category>:** <explanation>

### New Rules (for errata)
- Rule N: <description>

### GitHub Issues to File
- [ ] <repo>: <issue title> — <impact>
```

## Where to Log

Read the argument to determine which skill's errata to update:

| Argument | Errata File |
|----------|-------------|
| `journal` (default) | `~/.claude/skills/journal/errata.md` |
| `kusto` | `~/.claude/skills/kusto/errata.md` |
| `expenses` | `~/.claude/skills/expenses/errata.md` |
| other | Create `~/.claude/skills/<name>/errata.md` if it doesn't exist |

If no argument is provided, infer the skill from which MCP tools were used in the session (journal tools → journal, kusto tools → kusto, etc.).

Write directly to `~/.claude/skills/<name>/errata.md`.

## Steps

1. **Read** the existing errata file for the target skill (to get the next improvement number and avoid duplicates)
2. **Analyze** the conversation — build the timeline table by reviewing every tool call
3. **Present** the retro summary to the user for review
4. **On approval**, append the errata entry and any new improvement rules to the file
5. **Offer** to file GitHub issues for server-side problems (per the skill's `retro.md`)

## Rules

- Be honest about mistakes — don't minimize or rationalize
- Compare to the **optimal path**, not just "it eventually worked"
- Only log **actionable** improvements — rules that would change behavior next time
- Number new improvements sequentially from the last entry in the errata file
- Don't log trivial one-off mistakes that are unlikely to recur

## Errata Entry Template

When adding a new errata entry to the skill's `errata.md`, use this format:

```markdown
### YYYY-MM-DD: <short description> — N wasted calls

**User asked:** "<the query>"

**What went wrong:**

| Round | Calls | What I Did | Result |
|-------|-------|-----------|--------|
| 1 | N | <action> | SUCCESS/FAIL: <reason> |

**Total:** X calls (Y wasted). Should have been **Z calls in W rounds**.

**Optimal path:**
1. <step>
2. <step>

**Root causes:**
1. **<category>:** <explanation>

**Fix applied:** Added rule N in Improvements section / Filed issue #N.
```

## Improvement Entry Template

When a new rule emerges from an errata entry, add it to the Improvements section of the skill's `errata.md`:

```markdown
### N. <Rule Name> (Priority)

**Problem:** <what friction occurred>

**Rule:** <concrete instruction to follow>
```

Number sequentially from existing improvements. Mark priority as High/Medium/Low.

## Graduation Criteria

Move rules from a skill's `errata.md` → `gotchas.md` or `SKILL.md` when ALL of these are true:

- The same rule has prevented repeat mistakes across **2+ sessions**
- The rule is **stable** (not likely to change with server updates)
- The rule is **general** (applies to most queries, not edge cases)

Graduated rules belong in the skill's main instructions where they become part of standard guidance.

## GitHub Issue Filing

### When to File

File an issue on the appropriate repo when:

- A tool call fails due to **server behavior** (not user error)
- Multiple tool calls are needed for what should be **one operation**
- Schema doesn't expose fields needed for **common queries**
- Error messages are **unhelpful** for diagnosing the issue
- Include/hydration doesn't return **expected nested data**

### Where to File

Read the skill's `retro.md` file at `~/.claude/skills/<skill>/retro.md` for the GitHub repo mapping. Each skill's retro.md lists the MCP server repos and labels to use.

### Bug Template

- **Title:** Short, specific symptom
- **Body:**
  - Steps to reproduce: exact tool calls + inputs
  - Expected vs actual behavior
  - Full error text/stack if available
- **Labels:** `bug`

### Enhancement Template

```markdown
## Problem

[What friction/workaround was needed]

## Current Behavior

[How it works now, including limitations]

## Proposed Solution

[Specific fields, tables, or behavior to add]

## Impact

[How this reduces tool calls or improves UX]

## Example Use Case

[Concrete example from workflow]
```

- **Labels:** `enhancement` (add `documentation` if tool descriptions need updating)
