"""
Entity Delete/Restore Handlers

Unified routing handlers for delete_entity and restore_entity.
Consolidates 23 individual delete/undelete handlers (14 delete + 9 undelete).

Both handlers are registered as needs_db=True, needs_repos=True so internal
dispatch can use whichever is needed per entity type.
"""

import json
import logging
from typing import Any
from uuid import UUID
from mcp import types

logger = logging.getLogger(__name__)


async def handle_delete_entity(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete any entity by type and ID."""
    try:
        entity_type = arguments.get("entity_type")
        entity_id_str = arguments.get("entity_id")

        if not entity_type or not entity_id_str:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "entity_type and entity_id are required"}, indent=2)
            )]

        entity_id = UUID(entity_id_str)

        if entity_type == "exercise":
            await repos.exercises.soft_delete(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "exercise", "entity_id": entity_id_str,
                "message": "✅ Exercise deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type == "location":
            await repos.locations.soft_delete(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "location", "entity_id": entity_id_str,
                "message": "✅ Location deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type in ("event", "workout"):
            # Workouts and generic events are both deleted by marking the event as deleted
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE events SET is_deleted = TRUE, deleted_at = NOW() "
                    "WHERE id = $1 RETURNING id, title",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"{entity_type} with ID {entity_id_str} not found"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": entity_type, "entity_id": entity_id_str,
                "title": row["title"],
                "message": f"✅ {entity_type.title()} deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type == "meal":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE meals SET is_deleted = TRUE, deleted_at = NOW() "
                    "WHERE id = $1 RETURNING id, meal_title",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Meal with ID {entity_id_str} not found"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "meal", "entity_id": entity_id_str,
                "meal_title": row["meal_title"],
                "message": "✅ Meal deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type == "commute":
            async with db.pool.acquire() as conn:
                commute = await conn.fetchrow(
                    "SELECT c.id, e.title FROM commutes c JOIN events e ON c.event_id = e.id "
                    "WHERE c.event_id = $1 AND c.is_deleted = FALSE",
                    entity_id
                )
                if not commute:
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": f"Commute with event_id {entity_id_str} not found or already deleted"
                    }, indent=2))]
                await conn.execute(
                    "UPDATE commutes SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW() "
                    "WHERE event_id = $1",
                    entity_id
                )
                await conn.execute(
                    "UPDATE events SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW() "
                    "WHERE id = $1",
                    entity_id
                )
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "commute", "entity_id": entity_id_str,
                "title": commute["title"],
                "message": "✅ Commute deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type == "person":
            result = await repos.people.delete_person(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "person", "entity_id": entity_id_str,
                "canonical_name": result["canonical_name"],
                "message": "✅ Person deleted (soft delete — restore with restore_entity)"
            }, indent=2, default=str))]

        elif entity_type == "person_relationship":
            result = await repos.people.delete_relationship(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "person_relationship", "entity_id": entity_id_str,
                "note": "Hard delete — relationship permanently removed (reciprocal also deleted by trigger)",
                "message": "✅ Relationship deleted"
            }, indent=2, default=str))]

        elif entity_type == "person_residence":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE person_residences SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP "
                    "WHERE id = $1 AND is_deleted = FALSE RETURNING id, person_id",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Residence record {entity_id_str} not found or already deleted"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "person_residence", "entity_id": entity_id_str,
                "person_id": str(row["person_id"]),
                "message": "✅ Person residence deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type == "journal_entry":
            result = await repos.journal.delete_entry(entity_id)
            # Also remove from vector store if enabled
            if repos.memory.config.enabled and repos.memory.collection:
                try:
                    repos.memory.collection.delete(ids=[entity_id_str])
                    logger.info(f"Removed journal entry {entity_id_str} from vector store")
                except Exception as e:
                    logger.warning(f"Failed to remove from vector store: {e}")
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "journal_entry", "entity_id": entity_id_str,
                "message": "✅ Journal entry deleted (soft delete — restore with restore_entity)"
            }, indent=2))]

        elif entity_type == "health_condition":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE health_conditions SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP "
                    "WHERE id = $1 AND is_deleted = FALSE RETURNING id",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Health condition {entity_id_str} not found or already deleted"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "health_condition", "entity_id": entity_id_str,
                "message": "✅ Health condition deleted"
            }, indent=2))]

        elif entity_type == "medicine":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE health_medicines SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP "
                    "WHERE id = $1 AND is_deleted = FALSE RETURNING id",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Medicine log {entity_id_str} not found or already deleted"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "medicine", "entity_id": entity_id_str,
                "message": "✅ Medicine log deleted"
            }, indent=2))]

        elif entity_type == "supplement":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE health_supplements SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP "
                    "WHERE id = $1 AND is_deleted = FALSE RETURNING id",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Supplement log {entity_id_str} not found or already deleted"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "supplement", "entity_id": entity_id_str,
                "message": "✅ Supplement log deleted"
            }, indent=2))]

        elif entity_type == "health_condition_log":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE health_condition_logs SET is_deleted = TRUE, deleted_at = NOW() "
                    "WHERE id = $1 AND is_deleted = FALSE RETURNING id",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Health condition log {entity_id_str} not found or already deleted"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "health_condition_log", "entity_id": entity_id_str,
                "message": "✅ Health condition log deleted"
            }, indent=2))]

        else:
            return [types.TextContent(type="text", text=json.dumps({
                "error": f"Unknown entity_type: {entity_type}"
            }, indent=2))]

    except Exception as e:
        logger.error(f"Error in delete_entity: {e}", exc_info=True)
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"Error deleting {arguments.get('entity_type', 'entity')}: {str(e)}"
        }, indent=2))]


async def handle_restore_entity(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Restore a soft-deleted entity by type and ID."""
    try:
        entity_type = arguments.get("entity_type")
        entity_id_str = arguments.get("entity_id")

        if not entity_type or not entity_id_str:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "entity_type and entity_id are required"}, indent=2)
            )]

        entity_id = UUID(entity_id_str)

        if entity_type == "exercise":
            await repos.exercises.undelete(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "exercise", "entity_id": entity_id_str,
                "message": "✅ Exercise restored"
            }, indent=2))]

        elif entity_type == "location":
            await repos.locations.undelete(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "location", "entity_id": entity_id_str,
                "message": "✅ Location restored"
            }, indent=2))]

        elif entity_type in ("event", "workout"):
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE events SET is_deleted = FALSE, deleted_at = NULL "
                    "WHERE id = $1 RETURNING id, title",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"{entity_type} with ID {entity_id_str} not found"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": entity_type, "entity_id": entity_id_str,
                "title": row["title"],
                "message": f"✅ {entity_type.title()} restored"
            }, indent=2))]

        elif entity_type == "meal":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE meals SET is_deleted = FALSE, deleted_at = NULL "
                    "WHERE id = $1 RETURNING id, meal_title",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Meal with ID {entity_id_str} not found"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "meal", "entity_id": entity_id_str,
                "meal_title": row["meal_title"],
                "message": "✅ Meal restored"
            }, indent=2))]

        elif entity_type == "commute":
            async with db.pool.acquire() as conn:
                commute = await conn.fetchrow(
                    "SELECT c.id, e.title FROM commutes c JOIN events e ON c.event_id = e.id "
                    "WHERE c.event_id = $1 AND c.is_deleted = TRUE",
                    entity_id
                )
                if not commute:
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": f"Deleted commute with event_id {entity_id_str} not found"
                    }, indent=2))]
                await conn.execute(
                    "UPDATE commutes SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW() "
                    "WHERE event_id = $1",
                    entity_id
                )
                await conn.execute(
                    "UPDATE events SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW() "
                    "WHERE id = $1",
                    entity_id
                )
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "commute", "entity_id": entity_id_str,
                "title": commute["title"],
                "message": "✅ Commute restored"
            }, indent=2))]

        elif entity_type == "person":
            result = await repos.people.undelete_person(entity_id)
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "person", "entity_id": entity_id_str,
                "canonical_name": result["canonical_name"],
                "message": "✅ Person restored"
            }, indent=2, default=str))]

        elif entity_type == "person_residence":
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "UPDATE person_residences SET is_deleted = FALSE, deleted_at = NULL "
                    "WHERE id = $1 AND is_deleted = TRUE RETURNING id, person_id",
                    entity_id
                )
            if not row:
                return [types.TextContent(type="text", text=json.dumps({
                    "error": f"Deleted residence record {entity_id_str} not found"
                }, indent=2))]
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "person_residence", "entity_id": entity_id_str,
                "person_id": str(row["person_id"]),
                "message": "✅ Person residence restored"
            }, indent=2))]

        elif entity_type == "journal_entry":
            result = await repos.journal.undelete_entry(entity_id)
            # Re-index in vector store if enabled
            if repos.memory.config.enabled and repos.memory.collection:
                try:
                    entry = await repos.journal.get_by_id(entity_id)
                    if entry:
                        embedding = repos.memory._generate_embedding(entry.raw_text)
                        date_int = entry.entry_date.year * 10000 + entry.entry_date.month * 100 + entry.entry_date.day
                        metadata = {
                            "date": str(entry.entry_date),
                            "date_int": date_int,
                            "type": entry.entry_type,
                            "tags": ",".join(entry.tags) if entry.tags else ""
                        }
                        repos.memory.collection.add(
                            ids=[entity_id_str],
                            documents=[entry.raw_text],
                            embeddings=[embedding],
                            metadatas=[metadata]
                        )
                        logger.info(f"Re-indexed journal entry {entity_id_str} in vector store")
                except Exception as e:
                    logger.warning(f"Failed to re-index in vector store: {e}")
            return [types.TextContent(type="text", text=json.dumps({
                "entity_type": "journal_entry", "entity_id": entity_id_str,
                "message": "✅ Journal entry restored and re-indexed"
            }, indent=2))]

        else:
            return [types.TextContent(type="text", text=json.dumps({
                "error": f"restore not supported for entity_type: {entity_type}"
            }, indent=2))]

    except Exception as e:
        logger.error(f"Error in restore_entity: {e}", exc_info=True)
        return [types.TextContent(type="text", text=json.dumps({
            "error": f"Error restoring {arguments.get('entity_type', 'entity')}: {str(e)}"
        }, indent=2))]
