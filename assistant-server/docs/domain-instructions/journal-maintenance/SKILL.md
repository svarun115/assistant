---
name: journal-maintenance
description: Audit, export, and maintain journal data. Use when user requests audits (missing Garmin links, duplicates), recreating day entries, data cleanup, schema design, or backup operations.
---

# Journal Maintenance

Audits, exports, and data maintenance operations.

## Supported Actions

### 1. Audit Workouts Missing Garmin Links

Find workouts that should be linked to Garmin:

```sql
SELECT e.id AS event_id, e.title, e.start_time, w.category, w.sport_type
FROM events e
JOIN workouts w ON e.id = w.event_id
WHERE e.external_event_id IS NULL
  AND w.category IN ('running', 'cycling', 'walking', 'hiking', 'swimming')
ORDER BY e.start_time DESC;
```

**Linking procedure:**
1. For each unlinked workout, query Garmin for that date + type
2. Match by start time (±15 min) and distance (±10%)
3. If confident match: update with `external_event_id`
4. If ambiguous: list candidates, ask user

### 2. Audit Duplicate People

```sql
-- Same name duplicates
SELECT canonical_name, COUNT(*) 
FROM people 
WHERE COALESCE(is_deleted, false) = false
GROUP BY canonical_name 
HAVING COUNT(*) > 1;

-- Alias overlaps
SELECT p1.id, p1.canonical_name, p2.id, p2.canonical_name
FROM people p1, people p2
WHERE p1.id < p2.id
  AND COALESCE(p1.is_deleted, false) = false
  AND COALESCE(p2.is_deleted, false) = false
  AND (p1.canonical_name ILIKE '%' || p2.canonical_name || '%'
       OR p1.aliases && p2.aliases);
```

**Resolution:** Identify canonical record (more relationships/history), report to user, merge only with approval.

### 3. Audit Duplicate Locations

```sql
-- Same place_id
SELECT place_id, COUNT(*), array_agg(canonical_name)
FROM locations
WHERE place_id IS NOT NULL
  AND COALESCE(is_deleted, false) = false
GROUP BY place_id
HAVING COUNT(*) > 1;

-- Similar names without place_id
SELECT l1.id, l1.canonical_name, l2.id, l2.canonical_name
FROM locations l1, locations l2
WHERE l1.id < l2.id
  AND COALESCE(l1.is_deleted, false) = false
  AND COALESCE(l2.is_deleted, false) = false
  AND l1.place_id IS NULL AND l2.place_id IS NULL
  AND l1.canonical_name ILIKE '%' || l2.canonical_name || '%';
```

### 4. Recreate Day's Journal Entry

Export a day's data as readable text.

**Personal Review (Default):**
- File: `exports/YYYY_MM_DD_recreated.txt`
- Primary: RAW JOURNAL ENTRIES (verbatim)
- Secondary: DB details not in raw text (as addendum)

```sql
-- Raw journal entries
SELECT raw_text, created_at 
FROM journal_entries 
WHERE entry_date = '[date]'
ORDER BY created_at;

-- Structured events
SELECT e.title, e.start_time, e.end_time, e.notes,
       l.canonical_name as location,
       array_agg(p.canonical_name) as participants
FROM events e
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN event_participants ep ON e.id = ep.event_id
LEFT JOIN people p ON ep.person_id = p.id
WHERE e.start_time::date = '[date]'
  AND COALESCE(e.is_deleted, false) = false
GROUP BY e.id, l.canonical_name
ORDER BY e.start_time;
```

**Shareable Curated Recap (Explicit Request Only):**
- File: `exports/YYYY_MM_DD_curated.txt`
- Heavily curated, concise, readable
- No internal IDs, no giant verbatim blocks

### 5. Schema/Workflow Design

1. Gather requirements
2. Review schema: `mcp_personal_jour_get_database_schema()`
3. Propose changes with rationale
4. Draft migration if needed

### 6. Backup Operations

```
activate_database_backup_tools()
→ list_backups()
→ mcp_personal_jour_request_restore(backup_name, reason)
```

## Error Handling

**CRITICAL:** If any tool/DB error occurs:
1. STOP immediately
2. Report: what was attempted, inputs used, error text
3. Do NOT invent workarounds
4. Ask user how to proceed

## Output Format

```
Mode: ACTION

Action: [What was requested]

Findings:
- [Bullet list]

Proposed Changes:
- [What will be modified]

Awaiting Approval: Yes/No
```

Always await approval for destructive actions.

## Resource Files

For detailed procedures, see:
- [VERIFICATION-QUERIES.md](VERIFICATION-QUERIES.md) — SQL audit queries for data quality
- [OUTPUT-FORMATS.md](OUTPUT-FORMATS.md) — Day summary and export formats
