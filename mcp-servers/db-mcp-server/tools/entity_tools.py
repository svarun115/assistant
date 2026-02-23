"""
Entity Delete/Restore MCP Tools

Unified delete_entity and restore_entity consolidating 23 individual delete/undelete tools.
"""

from mcp import types


def get_entity_tools() -> list[types.Tool]:
    return [_delete_entity_tool(), _restore_entity_tool()]


def _delete_entity_tool() -> types.Tool:
    return types.Tool(
        name="delete_entity",
        description="""Soft delete any entity by type and ID.

Marks the entity as deleted (is_deleted=TRUE) but preserves all data for audit/recovery.
Deleted entities are excluded from queries and searches.

ENTITY TYPES:
- event: Generic/sleep/reflection/work event (pass the event_id)
- workout: Workout (pass the workout's event_id)
- meal: Meal record (pass the meal_id returned by create_meal)
- commute: Commute record (pass the commute's event_id)
- exercise: Exercise from exercise catalog (pass exercise_id)
- location: Location record (pass location_id)
- person: Person record — soft delete, preserves all history (pass person_id)
- person_relationship: Relationship between two people — WARNING: HARD DELETE, cannot be restored (pass relationship_id)
- person_residence: Person residence history record (pass residence_id)
- journal_entry: Journal entry — also removed from semantic search index (pass entry_id)
- health_condition: Health condition record (pass condition_id)
- medicine: Medicine log entry (pass medicine_id)
- supplement: Supplement log entry (pass supplement_id)
- health_condition_log: Health condition progression log (pass log_id)

EXAMPLES:
  delete_entity(entity_type="meal", entity_id="<meal-uuid>")
  delete_entity(entity_type="workout", entity_id="<event-uuid>")
  delete_entity(entity_type="person", entity_id="<person-uuid>")
  delete_entity(entity_type="health_condition", entity_id="<condition-uuid>")
""",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": [
                        "exercise", "location", "event", "workout", "meal", "commute",
                        "person", "person_relationship", "person_residence",
                        "journal_entry", "health_condition", "medicine", "supplement",
                        "health_condition_log"
                    ],
                    "description": "Type of entity to delete"
                },
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity to delete"
                }
            },
            "required": ["entity_type", "entity_id"]
        }
    )


def _restore_entity_tool() -> types.Tool:
    return types.Tool(
        name="restore_entity",
        description="""Restore a soft-deleted entity by type and ID.

Reverses a previous delete_entity call. Health entities (health_condition, medicine,
supplement, health_condition_log) and person_relationship do not support restore.

SUPPORTED ENTITY TYPES:
- event: Generic/sleep/reflection/work event (pass the event_id)
- workout: Workout (pass the workout's event_id)
- meal: Meal record (pass the meal_id)
- commute: Commute record (pass the commute's event_id)
- exercise: Exercise from exercise catalog
- location: Location record
- person: Person record
- person_residence: Person residence history record
- journal_entry: Journal entry — also re-indexed in semantic search

NOT SUPPORTED (no restore):
- health_condition, medicine, supplement, health_condition_log, person_relationship

EXAMPLES:
  restore_entity(entity_type="meal", entity_id="<meal-uuid>")
  restore_entity(entity_type="workout", entity_id="<event-uuid>")
  restore_entity(entity_type="journal_entry", entity_id="<entry-uuid>")
""",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": [
                        "exercise", "location", "event", "workout", "meal", "commute",
                        "person", "person_residence", "journal_entry"
                    ],
                    "description": "Type of entity to restore"
                },
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity to restore"
                }
            },
            "required": ["entity_type", "entity_id"]
        }
    )
