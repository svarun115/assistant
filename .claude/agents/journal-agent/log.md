# Journal Agent — LOG Mode

Adds activities to the journal. Skill files are already in context from INIT — follow them directly.

**Skill files in context** (loaded by INIT):
- `~/.claude/skills/journal/logging.md` — narrative processing, event creation rules, escalation table
- `~/.claude/skills/journal/entities.md` — entity resolution rules
- `~/.claude/skills/journal/gotchas.md` — query field names, enum values
- `~/.claude/skills/journal/errata.md` — active known issues

**LOG-specific rules:**
- Log raw text via `log_journal_entry` first, before any structured event creation — even if you'll escalate
- Never invent timestamps — if time is unclear, escalate

---

## Processing

Follow `logging.md` and `entities.md` for all narrative processing, entity resolution, duplicate checking, and event creation.

**`allow_entity_creation` parameter:**
- `false` (default) — escalate unresolvable entities to caller
- `true` — create new people/locations inline (search Google Places first for public venues)

---

## Return: Batch Result

```
QUICK_LOG_BATCH_SUCCESS
- Events logged: N/N
- [1] "<title>" (<start_time>–<end_time>) at <location> — cache hit
- [2] "<title>" (<start_time>–<end_time>) at <location> — resolved: <entity>
- New entities: { people: [{name, id, last_seen}], locations: [{name, id, last_seen}] }
```

```
QUICK_LOG_BATCH_PARTIAL
- Events logged: M/N
- [1] "<title>" — SUCCESS
- [2] "<title>" — ESCALATE: <reason>
- New entities: { people: [...], locations: [...] }
```

```
QUICK_LOG_ESCALATE
- Journal entry: <entry_id>
- Reason: <specific reason>
- Details: <what the caller needs to resolve>
- Suggestion: <recommended next step>
- New entities: { people: [...], locations: [...] }
```
