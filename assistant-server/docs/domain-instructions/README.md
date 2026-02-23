# Domain Instructions

Reference documentation for the Journal Agent's domain-specific behaviors. These files are loaded by the Skills Loader (`skills.py`) and injected into the agent's system prompt based on detected intent.

## Architecture

Instructions use **progressive disclosure** to optimize token usage:

| Level | Loaded | Content |
|-------|--------|---------|
| **Base prompt** | Always | Core behaviors, journal owner, response style |
| **Primary skill** | When triggered | Logging, Querying, or Maintenance instructions |
| **Supporting skills** | As needed | Entities, Garmin, Gmail, Sources |

## Available Instructions

| Domain | Triggers On | File |
|--------|-------------|------|
| [Logging](journal-logging/SKILL.md) | User describes events to record | Primary |
| [Querying](journal-querying/SKILL.md) | Questions about past data | Primary |
| [Maintenance](journal-maintenance/SKILL.md) | Audits, exports, cleanup | Primary |
| [Entities](journal-entities/SKILL.md) | Resolving people/locations | Supporting |
| [Garmin](journal-garmin/SKILL.md) | Workout/Garmin linking | Supporting |
| [Gmail](journal-gmail/SKILL.md) | Transaction email context | Supporting |
| [Sources](journal-sources/SKILL.md) | Source conflict resolution | Supporting |

## Usage in Agent

The `SkillsLoader` class in `skills.py` handles loading:

```python
from skills import SkillsLoader

loader = SkillsLoader()
prompt = loader.build_system_prompt(session_state)
```

Instructions are loaded based on:
1. **Session mode** (LOG, QUESTION, ACTION) → Primary instruction
2. **Context needs** (has Garmin data, has receipts) → Supporting instructions
3. **Explicit triggers** (mentions "workout", "receipt") → Additional context

Claude Code will auto-discover these skills when working in this project.

### Claude API
Upload via Skills API (`/v1/skills` endpoints).

### Claude.ai
Zip each skill folder and upload via Settings > Features.

## Skill Format

Each skill has a `SKILL.md` with YAML frontmatter:

```markdown
---
name: skill-name-lowercase
description: Brief description of what this does and when Claude should use it.
---

# Skill Title

[Instructions for Claude]
```

### Naming Rules
- Max 64 characters
- Lowercase letters, numbers, hyphens only
- No reserved words: "anthropic", "claude"

### Description Guidelines
- Max 1024 characters
- Include **what** the skill does
- Include **when** to use it (trigger conditions)

## Workflow

1. **Mode Detection** (from top-level instructions)
   - LOG → triggers `journal-logging`
   - QUESTION → triggers `journal-querying`
   - ACTION → triggers `journal-maintenance`

2. **Skill Chaining**
   - `journal-logging` may reference `journal-entities`, `journal-garmin`
   - `journal-querying` may reference `journal-sources`
   - Skills reference each other by name

## Development

To add a new skill:
1. Create folder: `skill-name/`
2. Create `SKILL.md` with frontmatter
3. Add to README table
4. Test in Claude Code locally

## Related

- [Anthropic Skills Documentation](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Skills Cookbook](https://github.com/anthropics/claude-cookbooks/tree/main/skills)
