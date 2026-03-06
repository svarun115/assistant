# Personal Assistant — Claude.ai

Claude.ai project files for Varun's personal assistant. Migrating from Claude Code to Claude.ai for mobile-friendly access.

## Structure

```
claude.ai/
├── README.md
├── knowledge/                    ← Project knowledge files (upload to Claude.ai project)
│   └── user-context.md           ← Personal identity, family Journal IDs
└── skills/                       ← Claude.ai skills (each folder → ZIP → upload)
    └── journal/                  ← Journal log + query skill
        ├── Skill.md              ← Main skill (description, intent detection, load table)
        ├── journal-data-model.md ← Enum reference
        ├── entity-resolution/    ← Loaded on demand during entity resolution
        │   ├── common.md
        │   ├── people.md
        │   ├── locations.md
        │   └── exercises.md
        └── modes/                ← Loaded on demand by mode
            ├── log.md
            ├── reflect.md
            └── query.md
```

## Migration Plan

See [claude-ai-migration.md](https://github.com/svarun115/assistant/blob/master/.claude/plans/persistent/claude-ai-migration.md) in the assistant repo.

## MCP Servers

Skills connect to these MCP servers (deployed on Azure VM behind OAuth 2.1 gateway):
- `personal-journal` — events, people, locations, workouts, meals
- `garmin` — fitness data, sleep, body battery
- `google-places` — location search/details
- `google-workspace` — calendar, tasks, Gmail
