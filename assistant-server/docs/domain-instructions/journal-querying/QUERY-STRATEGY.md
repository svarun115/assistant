# Query Strategy Guide: SQL vs Semantic Search

## Overview

This guide explains when to use SQL queries versus semantic search when querying the personal journal database, and how to leverage both for comprehensive answers.

## Quick Decision Matrix

| Query Type | Primary Tool | Why |
|------------|-------------|-----|
| "When did I last run at KBR Park?" | SQL | Structured event with location - direct query |
| "When did I last speak to Amma and Appa?" | SQL | Structured event with participants - direct query |
| "How many workouts did I do in August?" | SQL | Precise counting of structured events |
| "Who did I meet for meals in July?" | SQL | Structured relationship queries |
| "What was I feeling anxious about?" | Semantic Search | Emotional context in journal narratives |
| "Show my training volume by week" | SQL | Quantitative aggregations |
| "What happened when Gauri had her biopsy?" | Semantic Search → SQL | Story/context query, then verify timeline |
| "List all locations I visited on Aug 15" | SQL | Structured event data with precise date |
| "How have I been sleeping lately?" | Semantic Search + SQL | Narrative context + structured sleep quality scores |

---

## When to Use Semantic Search

**Best for:**
- Natural language questions about experiences, feelings, or stories
- Understanding context, motivations, and narrative flow
- Finding mentions of people, events, or topics without knowing exact dates
- Exploring themes (anxiety, career, relationships, health concerns)
- Questions starting with "How have I been...", "What was I thinking about...", "Tell me about..."

**Characteristics:**
- Returns full journal text entries with context
- Uses AI embeddings to understand meaning, not just keywords
- Great for fuzzy/exploratory searches
- Provides rich narrative details
- Can find related concepts even with different wording

**Example Queries:**
```
- "What workouts caused knee pain?"
- "How did I feel about job applications?"
- "What did Anup say about spirituality?"
- "Tell me about my pet project progress"
- "What was I anxious about last week?"
```

---

## When to Use SQL

**Best for:**
- Counting, summing, averaging (quantitative analysis)
- Precise date/time filtering
- Relationship queries (who was with me, where was I)
- Structured data extraction (workout exercises, meal items, medication logs)
- Validation and verification of specific facts
- Finding patterns across structured fields

**Characteristics:**
- Returns structured data in tables/rows
- Fast and precise with indexed columns
- Excellent for aggregations and calculations
- Enforces data integrity
- Can join across related tables (events, people, locations, workouts)

**Example Queries:**
```sql
-- When did I last speak to Amma?
SELECT e.start_time, e.title, e.notes
FROM events e
JOIN event_participants ep ON ep.event_id = e.id
JOIN people p ON ep.person_id = p.id
WHERE p.canonical_name = 'Amma'
ORDER BY e.start_time DESC LIMIT 1;

-- Count workouts by month
SELECT DATE_TRUNC('month', start_time) as month, COUNT(*) 
FROM events WHERE event_type = 'workout' GROUP BY month;

-- Find all meals with Mohit
SELECT e.start_time, e.title, l.canonical_name 
FROM events e 
JOIN event_participants ep ON ep.event_id = e.id
JOIN people p ON ep.person_id = p.id
LEFT JOIN locations l ON e.location_id = l.id
WHERE p.canonical_name ILIKE '%Mohit%' AND e.category = 'social';
```

---

## Hybrid Approach: Best Practice Workflow

For most queries, use **both tools in sequence** for comprehensive and verified answers:

### Workflow Pattern:

```
1. UNDERSTAND THE QUESTION
   - Is it exploratory (semantic) or quantitative (SQL)?
   - Does it need context or just facts?

2. PRIMARY QUERY
   - Semantic: Get narrative context and approximate dates
   - SQL: Get precise structured data

3. CROSS-VERIFY
   - Use the other tool to validate findings
   - Check for consistency between narrative and structured data

4. FLAG DISCREPANCIES
   - If findings don't match, investigate further
   - Present both results to user for clarification

5. CORRECT IF NEEDED
   - After user confirms the correct version, update the incorrect source
   - Document the correction
```

### Example: "What did I discuss with Anup about spirituality?"

**Step 1: Semantic Search**
```
Query: "What did Anup say about spirituality?"
Result: Aug 13, 2025 - "Anup is well-read in astrology, spirituality, and palmistry..."
```

**Step 2: SQL Verification**
```sql
SELECT e.start_time, e.title, e.notes, p.canonical_name
FROM events e
JOIN event_participants ep ON ep.event_id = e.id
JOIN people p ON ep.person_id = p.id
WHERE p.canonical_name ILIKE '%Anup%'
  AND DATE(e.start_time) = '2025-08-13'
ORDER BY e.start_time;
```

**Step 3: Compare**
- Does the SQL show an event with Anup on August 13?
- Do the event notes contain context about the conversation?
- Was this a work meeting or personal discussion?

**Step 4: Report to User**
```
✅ VERIFIED: Conversation with Anup on Aug 13, 2025
   - Event: One-on-one meeting (4:30-5:15 PM)
   - Topics: Astrology, spirituality, palmistry, meditation, stress
   - Key insight: "Stress caused when wants exceed capacity"
   - Note: Initially scheduled to discuss Copilot Health, became philosophical
```

---

## Common Discrepancy Scenarios

### 1. Missing Structured Event for Journal Entry

**Symptom:** Semantic search finds a journal entry describing an event, but SQL shows no corresponding event record.

**Action:**
```
1. Show both results to user
2. Ask: "Your journal mentions [event] on [date], but I don't see it in structured events. Should I create it?"
3. If confirmed, create the missing event with proper structure
```

### 2. Date/Time Mismatch

**Symptom:** Journal says "spoke to Gauri at 8 PM" but event shows 7:30 PM.

**Action:**
```
1. Present both timestamps to user
2. Ask which is correct
3. Update the incorrect source
4. Log correction in notes
```

### 3. Participant Missing from Event

**Symptom:** Journal mentions "dinner with Mohit and Sharath" but event only links Mohit.

**Action:**
```
1. Highlight the discrepancy
2. Confirm with user if Sharath should be added
3. Update event_participants table
4. Note: "Added Sharath based on journal cross-check"
```

### 4. Conflicting Quantitative Data

**Symptom:** Journal says "ran 12K" but workout_event shows 10.5K distance.

**Action:**
```
1. Present both values
2. Check if there's a Garmin sync (external_event_id) - trust Garmin if present
3. Ask user which is accurate
4. Update and document source of truth
```

### 5. Location Name Variations

**Symptom:** Journal mentions "Building 4 Cafeteria", "Melopedia", "office cafeteria" for same place.

**Action:**
```
1. Use location resolution to find canonical name
2. If ambiguous, query user
3. Add aliases to location notes for future reference
4. Update journal entry tags if needed
```

---

## Data Integrity Guidelines

### Always Cross-Verify When:
- ✅ Creating new structured events from journal text
- ✅ User asks for specific counts or statistics
- ✅ Investigating patterns or trends
- ✅ User questions the accuracy of previous data
- ✅ Processing historical journal entries

### Can Skip Cross-Verification When:
- ⚠️ Pure exploratory/narrative questions ("tell me about...")
- ⚠️ User explicitly asks for only journal text
- ⚠️ Quick context queries during data entry

### Correction Protocol:

1. **Identify Discrepancy**
   - Note exactly what differs between sources
   - Include timestamps, IDs, and specific values

2. **Present to User**
   ```
   ⚠️ DISCREPANCY FOUND:
   - Journal (2025-08-15): "ran 12K at KBR Park"
   - Database Event: 10.5K distance logged
   - Garmin Activity 20012345: 12.01K
   
   Which should I trust as source of truth?
   ```

3. **Execute Correction**
   - Update the incorrect source
   - Add note: "Corrected [field] from [old] to [new] based on [source] (verified 2025-12-12)"
   - Log in a corrections table if needed

4. **Learn Pattern**
   - If same type of discrepancy repeats, note systemic issue
   - Update processing instructions to prevent future occurrences

---

## Query Examples by Complexity

### Simple (Single Tool)

**Semantic:**
- "What did I eat for dinner on August 10?"
- "How was I feeling about my job?"

**SQL:**
```sql
-- Count events by type
SELECT event_type, COUNT(*) FROM events GROUP BY event_type;

-- Find recent workouts
SELECT start_time, title FROM events 
WHERE event_type = 'workout' ORDER BY start_time DESC LIMIT 10;
```

### Moderate (Hybrid)

**Query:** "How often did I work out with Mohit in August?"

1. **Semantic:** Search for workout mentions with Mohit to understand context
2. **SQL:** Count exact workout events with Mohit as participant
3. **Cross-verify:** Ensure all narrative mentions have corresponding events

### Complex (Multi-Stage)

**Query:** "What's the relationship between my sleep quality and next-day workout performance?"

1. **SQL:** Extract sleep quality scores and next-day workout data
2. **Semantic:** Search for journal mentions of feeling tired, energetic, etc.
3. **Correlate:** Match quantitative scores with qualitative descriptions
4. **Present:** Combined analysis showing patterns

---

## Tool-Specific Best Practices

### Semantic Search

**DO:**
- Use natural, conversational language
- Search for concepts and themes, not just keywords
- Use date filters when you know approximate timeframes
- Request multiple results to see context across dates

**DON'T:**
- Expect precise counts or calculations
- Assume completeness (may not find every mention)
- Use for validation without SQL cross-check

### SQL Queries

**DO:**
- Use views for common query patterns (get_person_details, etc.)
- Include date ranges to limit result size
- Join to get rich context (person names, location names)
- Use ILIKE for case-insensitive string matching

**DON'T:**
- Forget to check for NULL values in optional fields
- Assume data exists without checking first
- Query without understanding schema relationships

---

## Schema Quick Reference

Key tables for cross-verification:

```sql
-- Core event data
events (id, title, start_time, end_time, event_type, location_id, category, notes)

-- Journal text
journal_entries (id, entry_date, raw_text, entry_type, tags)

-- Relationships
event_participants (event_id, person_id)
people (id, canonical_name, aliases, relationship, kinship_to_owner)
locations (id, canonical_name, place_id, location_type, notes)

-- Specializations
workouts (id, event_id, workout_name, category, sport_type)
meals (id, event_id, meal_title, meal_type)
commutes (id, event_id, from_location_id, to_location_id, transport_mode)

-- Health tracking
health_conditions (id, event_id, condition_name, severity, start_date)
health_medicines (id, event_id, medicine_name, dosage, log_date)
```

---

## Future Enhancements

Potential improvements to query workflow:

1. **Automatic Cross-Verification**
   - Tool that runs both queries automatically and flags discrepancies

2. **Confidence Scoring**
   - Rate how confident we are in answers based on source agreement

3. **Smart Correction Suggestions**
   - AI suggests which source is likely correct based on patterns

4. **Query Templates**
   - Pre-built hybrid queries for common question types

5. **Discrepancy Log**
   - Table tracking all corrections made and their reasoning

---

## Summary

**Golden Rule:** When precision matters, use SQL. When context matters, use semantic search. When both matter, use both.

Always prefer cross-verification for:
- Historical data entry/migration
- User-facing query answers
- Data quality validation
- Resolving ambiguities

The two tools are complementary, not competing. Together they provide both the quantitative rigor and qualitative richness needed for a complete personal journal system.
