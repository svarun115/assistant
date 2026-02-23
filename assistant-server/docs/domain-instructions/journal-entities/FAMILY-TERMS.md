# Family Term Resolution

Special handling for family relationship terms.

## Context-Based Interpretation

When narrative mentions "Amma/Appa/Mom/Dad":

**Key rule:** If most other people in the narrative belong to one family (e.g., Gauri's family: Vijay, Paru, Dhruv), interpret "Amma/Appa" as belonging to **that family context**, not the user's own parents.

Only default to user's own parents if:
- Context is clearly about user's family
- User is alone in the narrative

## Resolution Query

```sql
SELECT p.id, p.canonical_name, p.aliases,
       pr.relationship_type, pr.relationship_label,
       rp.canonical_name AS related_to
FROM people p
LEFT JOIN person_relationships pr ON p.id = pr.person_id
LEFT JOIN people rp ON pr.related_person_id = rp.id
WHERE COALESCE(p.is_deleted, false) = false
  AND (p.canonical_name ILIKE '%search_term%' OR 'SearchTerm' = ANY(p.aliases))
```

## Presentation Rules

**Always explain who each person is by relationship/context:**
- ✅ "Gauri's mother Lekshmy Chidambaram"
- ✅ "Sudha Nair (Amooma, maternal grandmother)"
- ❌ Never present UUIDs to user

## Verify Before Stating

Before describing relationships (e.g., "Gauri's brother"):
1. Query `person_relationships` to confirm actual relationship
2. Do not infer from co-presence alone

Example: Vijay at Gauri's parents' house with Paru doesn't make him Gauri's brother — check if he's Paru's spouse (making him brother-in-law).

## Alias Collision

If same alias matches multiple people:
- Do NOT guess
- Ask which record to use
- Avoid creating duplicates
