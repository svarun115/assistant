---
name: journal-querying
description: Answer questions about past journal data using SQL queries and semantic search. Use when user asks about past events, counts, frequencies, timelines, last time something happened, or how they felt about something.
---

# Journal Querying

Answer questions about past journal data using the two-shelves model.

## Two Shelves Model

| Shelf | Use For |
|-------|---------|
| **Structured (SQL)** | Counts, timelines, participants, locations, workout stats |
| **Unstructured (Semantic)** | Mood, feelings, themes, story recall, reflections |

## Decision Flow

```
Question Type?
├── FACTUAL (counts, dates, stats) → SQL Path
├── SEMANTIC (feelings, themes) → Search Path
└── HYBRID (both needed) → Combine
```

## SQL Path (Factual Questions)

### Common Query Patterns

**Last time X happened:**
```sql
SELECT e.start_time, e.title, e.notes
FROM events e
JOIN workouts w ON e.id = w.event_id
WHERE w.category = 'running'
ORDER BY e.start_time DESC
LIMIT 1;
```

**Frequency/counts:**
```sql
SELECT COUNT(*), DATE_TRUNC('week', start_time) as week
FROM events e
JOIN workouts w ON e.id = w.event_id
WHERE e.start_time >= NOW() - INTERVAL '30 days'
GROUP BY week
ORDER BY week;
```

**Who was involved:**
```sql
SELECT p.canonical_name, COUNT(*) as times
FROM event_participants ep
JOIN people p ON ep.person_id = p.id
WHERE ep.event_id IN (SELECT id FROM events WHERE ...)
GROUP BY p.canonical_name;
```

**Location history:**
```sql
SELECT l.canonical_name, COUNT(*) as visits
FROM events e
JOIN locations l ON e.location_id = l.id
WHERE e.start_time >= '[date]'
GROUP BY l.canonical_name
ORDER BY visits DESC;
```

### Garmin as Source of Truth

For workout stats (HR, pace, calories, elevation), **always prefer Garmin** when linked.

Query flow:
1. Get event with `external_event_id` from DB
2. Call `mcp_garmin_get_activity(activity_id)` for detailed stats
3. Use Garmin data in response

```sql
SELECT external_event_id FROM events 
WHERE id = '<uuid>' 
AND external_event_source = 'garmin';
```

## Semantic Search Path

Use for mood, feelings, themes:
```
mcp_personal_jour_search_journal_history(query, start_date, end_date, limit)
```

Good for:
- "How was I feeling about..."
- "What was that trip where..."
- "Tell me about the time..."

## Hybrid Questions

Some questions need both paths:
- "How many times did I run when stressed?" → SQL (run count) + Semantic (stress mentions)
- "What restaurants did I enjoy?" → SQL (locations) + Semantic (positive sentiment)

Strategy:
1. Get structured data first (IDs, dates, counts)
2. Enrich with semantic search on those date ranges
3. Synthesize answer

## Source Conflict Resolution

If sources disagree:
1. State both values explicitly
2. Label the discrepancy
3. Ask user which to trust

> "Your journal says you ran 8K, but Garmin shows 7.2K. Which should I use?"

See `journal-sources` skill for full priority rules.

## Response Format

```
Mode: QUESTION

Answer: [Direct answer to the question]

Sources:
- SQL: [what was queried]
- Semantic: [if used]
- Garmin: [if applicable]

Confidence: High/Medium/Low
```

## Error Handling

| Scenario | Action |
|----------|--------|
| No results | State clearly, suggest alternatives |
| Tool unavailable | Ask user to provide data |
| Ambiguous question | Ask ONE clarifying question |

## Resource Files

For detailed procedures, see:
- [QUERY-STRATEGY.md](QUERY-STRATEGY.md) — Decision matrix, hybrid workflows, discrepancy handling, correction protocol
