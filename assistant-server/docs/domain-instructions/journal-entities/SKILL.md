---
name: journal-entities
description: Resolve people and locations to prevent duplicates. Use when creating events with participants or locations, or when a name/place needs to be identified in the database.
---

# Entity Resolution

Prevent duplicate records and ensure correct entity linking.

## People Resolution

### Search Pattern (ALWAYS use this)

```sql
SELECT id, canonical_name, aliases
FROM people
WHERE canonical_name ILIKE '%[search_term]%'
   OR '[search_term]' = ANY(aliases)
   OR '[search_term]' ILIKE ANY(aliases);
```

### Resolution Flow

```
Name mentioned
    ↓
SQL search (name + aliases)
    ↓
├── 0 hits → Semantic search → Ask before creating
├── 1 hit → Verify relationship → Use it
└── Multiple → Query relationships → Ask ONE question
```

### Family Terms

| Term | Action |
|------|--------|
| Amma, Mom, Mother | Query `relationship_type = 'parent'` (female) |
| Appa, Dad, Father | Query `relationship_type = 'parent'` (male) |
| Wife, Husband, Spouse | Query `relationship_type = 'spouse'` |

**NEVER assume family relationships.** Always verify:
```sql
SELECT p.id, p.canonical_name, pr.relationship_type
FROM person_relationships pr
JOIN people p ON pr.related_person_id = p.id
WHERE pr.person_id = '[owner_person_id]'
  AND pr.relationship_type = 'parent';
```

### Duplicate Detection

If search returns multiple records that appear to be same person:
1. Check which has more relationships/event history
2. Flag duplicate for cleanup
3. Do NOT silently pick one
4. Report to user

### Creating New People

Only create if:
1. SQL search returned 0 results
2. Semantic search found no fuzzy matches
3. User confirmed it's a new person

Required: `canonical_name` (full name preferred)
Recommended: Add known aliases upfront

---

## Location Resolution

### For Public Venues (Restaurants, Gyms, Parks, Offices)

**MANDATORY: Get place_id first**

1. Search Google Places:
   ```
   mcp_google_places_search_places(query: "[venue] [city]")
   ```

2. Confirm with user if multiple results

3. Search DB by place_id:
   ```sql
   SELECT id, canonical_name, place_id
   FROM locations
   WHERE place_id = '[google_place_id]';
   ```

4. If exists: reuse. If not: create with place_id.

### For Private/Informal Locations

Skip place_id for residences, informal spots.

```sql
SELECT id, canonical_name, location_type
FROM locations
WHERE canonical_name ILIKE '%[name]%'
  AND location_type IN ('residence', 'private');
```

### Generic Terms

| Term | Resolution |
|------|------------|
| "home" | Query user's current residence for that date |
| "office" | Query user's workplace for that date |
| "gym" | Query most frequent gym around that date |
| "the usual" | Ask for clarification |

**Never create literal "Home" or "Office" location.**

### Forbidden Patterns

❌ Micro-locations: "my desk", "kitchen counter"
→ Use parent location, put detail in notes

❌ Vendor names for cafeterias: "Sodexo"
→ Use "Office Cafeteria" or building name

❌ Creating without place_id (for public venues)

### Creating New Locations

Required:
- `canonical_name`
- `place_id` (for public venues)
- `location_type`

---

## Validation Queries

Run periodically:

```sql
-- Orphan participants
SELECT ep.* FROM event_participants ep
LEFT JOIN people p ON ep.person_id = p.id
WHERE p.id IS NULL;

-- Duplicate place_ids
SELECT place_id, COUNT(*), array_agg(canonical_name)
FROM locations
WHERE place_id IS NOT NULL
GROUP BY place_id
HAVING COUNT(*) > 1;
```

## Resource Files

For detailed procedures, see:
- [FAMILY-TERMS.md](FAMILY-TERMS.md) — Context-based family term resolution
