# Output Formats

Standard formats for day summaries and exports.

## Day Summary (When User Asks)

Present in three sections:

### Section 1: Entity Resolution

List entities identified or created:
- **People:** names (and aliases) resolved/used as participants
- **Places:** locations created or reused; include `place_id` for public venues
- **Database links:** Garmin links, workout_id, meal_id created

Notes:
- Use structured shelf (SQL) as source of truth
- If entity was ambiguous, mention final resolution

### Section 2: Events Created (By Specialization)

Group by DB specialization:
- **Workouts** (note if Garmin-linked)
- **Meals**
- **Commutes**
- **Entertainment**
- **Generic events**
- **Sleep/Reflections/Work blocks**

For each: title, start/end time, **location**, key participants.

Location rules:
- Non-commute: show human-readable location name
- Commute: show **from → to** names
- Exception: event with commute as parent may omit location

### Section 3: Timeline

Chronological, one line per event:

**Non-commute:**
```
HH:MM–HH:MM — <type>: <title> @ <location> (participants)
```

**Commute:**
```
HH:MM–HH:MM — commute: <title> @ <from> → <to> (participants)
```

- No end time: `HH:MM — ...`
- Crosses midnight: show date on end time
- Sleep after midnight: separate line marked "Sleep (started)"

---

## Recreated Day Entry Export

### Clarify Goal First

- **Personal review (default):** confirm what was written + captured
- **Shareable recap (explicit request only):** curated for sharing

### File Location & Naming

Directory: `exports/`

| Type | Filename |
|------|----------|
| Personal review | `YYYY_MM_DD_recreated.txt` |
| Shareable recap | `YYYY_MM_DD_curated.txt` |

### Personal Review (Default)

**Content:**
1. **Primary:** RAW JOURNAL ENTRIES (verbatim) for that date
2. **Secondary:** DB ADDENDA (AI-generated) only if DB has details not in raw text:
   - Human-readable locations
   - Commutes as `from → to`
   - Meal item lists from `meal_items`
   - Participant names (no IDs)

**Rules:**
- Exclude soft-deleted records (`COALESCE(is_deleted, false) = false`)
- Do NOT generate full timeline unless explicitly asked
- No UUIDs in output

### Shareable Recap (Explicit Request Only)

**Rules:**
- Exclude soft-deleted records
- No internal UUIDs/IDs
- Curate heavily; keep concise and readable
- Human-readable locations, commutes as `from → to`
- Include meal items when available
- Avoid giant verbatim blocks unless asked
