# Entity Resolution — Common Rules

Before creating ANY event, resolve all entities. Prevents duplicates, ensures data integrity. Use the `query` tool for all searches. Soft-delete filtering is automatic.

---

## Deleting and Restoring Entities

All deletes go through `delete_entity(entity_type, entity_id)`. No separate `delete_person`, `delete_exercise`, etc. tools.

Supported types: `event`, `workout`, `meal`, `commute`, `exercise`, `location`, `person`, `person_relationship`, `person_residence`, `journal_entry`, `health_condition`, `medicine`, `supplement`, `health_condition_log`

Restore (most types — not health entities or `person_relationship`): `restore_entity(entity_type, entity_id)`

---

## Search Before Create (Always)

Before creating ANY entity (person, location, exercise), search first. This is non-negotiable.

## UUID Display Rule

**Never show UUIDs to the user.** Always present as "[Name] (your partner)", "[Name] (colleague at [Company])".

## Voice Journaling & Typos

Journal entries are often voice-transcribed. Common phonetic errors: "Jon" → "John", "Sara" → "Sarah". Strategy: search phonetically similar names, use context (workplace, recent events) to match. Do NOT add typos as aliases.

---

## Entity Resolution Gate (LOG Mode — MANDATORY)

### Phase 1: Discovery (read-only)

Run all searches in parallel:
- Search all people mentioned
- Search all locations mentioned
- Search all exercises (for workouts)

### Phase 2: Present Summary and Wait

```
Entity Resolution for [DATE]

People — Resolved:
| Narrative  | Match           | Relationship        |
| [Partner]  | [Full Name]     | Partner             |
| Mom        | [Mother's Name] | Partner's mother    |

People — NOT FOUND:
| Name    | Context          | Action                       |
| [Name]  | "met at cafe"    | Create? (colleague/friend?)  |

Locations — Resolved:
| Narrative   | Match             |
| [Park name] | [Full Park Name]  |

Should I proceed with these resolutions?
```

**WAIT for user confirmation before Phase 3.**

### Phase 3: Creation (only after confirmation)

1. Create confirmed new entities
2. Create events with resolved IDs
3. Log raw journal entry to semantic shelf
