# Entity Resolution — People

## Check user-context.md FIRST

The Family table in `user-context.md` has pre-resolved Journal IDs (UUIDs) and aliases for all close family and partner. If the person matches any name or alias there, use that UUID directly — **no DB query needed.**

## Search Pattern (MANDATORY)

Every people search MUST search both canonical name AND aliases, include relationships:
```
query(entity="people", where={"name": {"contains": "search_term"}}, include=["relationships"])
```
If no results: `where={"aliases": {"contains": "SearchTerm"}}`

## Relational Resolution

When someone is described as "[Person A]'s wife" or "[Partner]'s sibling" — don't escalate. Instead:
1. Get anchor person's UUID from cache or DB
2. Query their relationships: `query(entity="people", where={"id": {"eq": "<uuid>"}}, include=["relationships"])`
3. Match relationship type and use that person's ID

Escalate only if anchor has no matching relationship type, or multiple same-type matches.

## Family Terms (Mom/Dad and equivalents)

Context-dependent: if narrative mentions the partner's family, "Mom/Dad" may refer to the partner's parents, not the owner's. Default to owner's parents only if context is clearly about their own family. When uncertain: "When you say 'Dad', do you mean your father or [partner]'s father?"

## Relationship Graph Traversal

"How is X related to me?" — traverse up to 3 hops. Present path: "[Name] → [partner]'s mother → your mother-in-law." Only ask if no path found.

## Duplicate Detection

Multiple records for same person → check which has relationships/event history (that's canonical). Flag: "Found both '[Nickname]' and '[Full Name]' — using the one with event history." Never silently pick one.

## Merging Duplicate People

Use `merge_duplicate_people` — it handles event reassignment atomically:

1. Identify canonical record (more data/relationships/recent activity)
2. Run dry-run to preview: `merge_duplicate_people(canonical_person_id, duplicate_person_id, dry_run=true)`
3. Confirm with user, then execute: `merge_duplicate_people(..., dry_run=false)`

This reassigns all event participations and relationships, then soft-deletes the duplicate. No manual per-event updates needed.

## Creating New People

Before creating, MUST have: searched by name and aliases, searched semantically for typos/variants, presented findings to user, received explicit confirmation.

Placeholder for unnamed relatives: `[Person]'s Mother (name unknown)`, alias `[Person]'s mom`. Create relationship immediately.

## Personal History Capture

When user mentions biographical facts, use `add_person_detail(person_id, detail_type, fields)`:

| detail_type | Required fields |
|-------------|-----------------|
| `"work"` | company, role, location_id (UUID) |
| `"education"` | institution, degree, location_id (UUID) |
| `"residence"` | location_id (UUID), or temporal_location_id to reuse existing |
| `"note"` | text |
| `"relationship"` | related_person_id, relationship_type |

`person_notes` may supplement but must NOT be the only record for structured facts.
