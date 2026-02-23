"""
Travel Handlers
Handles: create_commute, update_commute, delete_commute, undelete_commute
All travel reads use execute_sql_query (SQL-first architecture).
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID
from mcp import types

from models import EventCreate, EventType, EventParticipant, Significance, CommuteCreate
from typing import Optional

logger = logging.getLogger(__name__)


def serialize_result(obj):
    """Helper to serialize datetime and other non-JSON types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def resolve_location(
    repos,
    location_id: Optional[str] = None
) -> Optional[UUID]:
    """
    Resolve location_id to UUID (no auto-create by name).
    """
    if location_id:
        try:
            location_uuid = UUID(location_id)
            location = await repos.locations.get_by_id(location_uuid)
            if not location:
                raise ValueError(f"Location not found: {location_id}")
            if getattr(location, 'is_deleted', False):
                raise ValueError(f"Location has been deleted: {location_id}")
            return location.id
        except ValueError as e:
            raise ValueError(f"Invalid location_id: {e}")
    return None


async def resolve_participants(
    repos,
    participant_names: list[str] = None,
    participant_ids: list[str] = None,
    role: str = "participant"
) -> list[EventParticipant]:
    """
    Resolve participants to EventParticipant objects via hybrid approach:
    - participant_names: Auto get_or_create() for each name
    - participant_ids: Validate each exists
    """
    participants = []
    
    if participant_names:
        for name in participant_names:
            person = await repos.people.get_or_create(name)
            participants.append(EventParticipant(person_id=person.id, person_name=name, role=role))
    
    if participant_ids:
        for person_id_str in participant_ids:
            person_id = UUID(person_id_str)
            person = await repos.people.get_by_id(person_id)
            if not person:
                raise ValueError(f"Person not found: {person_id_str}")
            participants.append(EventParticipant(person_id=person_id, person_name=person.canonical_name, role=role))
    
    return participants


def parse_datetime(dt_string: str) -> datetime:
    """Parse ISO 8601 datetime string"""
    if isinstance(dt_string, datetime):
        return dt_string
    return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))


async def handle_create_commute(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Create a commute with event (event-first architecture).
    
    Uses location IDs for commute endpoints:
    - from_location_id
    - to_location_id
    - participant_ids (participant_names no longer supported)
    """
    try:
        event_args = arguments["event"]
        commute_args = arguments["commute"]
        
        # Reject participant_names parameter (use participant_ids only)
        if "participant_names" in event_args:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'participant_names' is no longer supported. Use 'participant_ids' with UUIDs instead. Create people first using create_person tool if needed."
                }, indent=2)
            )]

        # Reject from/to_location_name (use from/to_location_id only)
        if "from_location_name" in commute_args or "to_location_name" in commute_args:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameters 'from_location_name'/'to_location_name' are no longer supported. Use 'from_location_id'/'to_location_id' (UUIDs) instead. If you only have names, call search_locations/create_location first, then pass the resulting IDs."
                }, indent=2)
            )]
        
        # Extract event fields
        title = event_args["title"]
        start_time = parse_datetime(event_args["start_time"])
        end_time = parse_datetime(event_args["end_time"]) if event_args.get("end_time") else None
        notes = event_args.get("notes")
        tags = event_args.get("tags", [])
        category = event_args.get("category", "travel")
        significance = event_args.get("significance", "routine")
        
        # Resolve participants using proper helper function
        participants = await resolve_participants(
            repos,
            participant_ids=event_args.get("participant_ids")
        )
        
        # Extract commute fields
        transport_mode = commute_args["transport_mode"]
        from_location_id = commute_args.get("from_location_id")
        to_location_id = commute_args.get("to_location_id")
        
        # Validate parent_event_id if provided
        parent_event_id = None
        if event_args.get("parent_event_id"):
            try:
                parent_event_id = UUID(event_args["parent_event_id"])
                # Verify parent event exists
                parent = await repos.events.get_by_id(parent_event_id)
                if not parent:
                    raise ValueError(f"Parent event with ID {event_args['parent_event_id']} not found or is deleted")
            except ValueError as e:
                raise ValueError(f"Invalid parent_event_id: {e}")
        
        resolved_from_location_id = await resolve_location(repos, from_location_id)
        resolved_to_location_id = await resolve_location(repos, to_location_id)
        
        # Create event using repository (handles participants via EventCreate)
        event = EventCreate(
            event_type=EventType.COMMUTE,
            title=title,
            description=event_args.get("description"),
            start_time=start_time,
            end_time=end_time,
            location_id=None,  # Commute uses from/to locations, not single location
            parent_event_id=parent_event_id,
            category=category,
            significance=Significance(significance),
            participants=participants,
            notes=notes,
            tags=tags
        )
        
        # Create commute with event via repository
        from models import CommuteCreate
        commute = CommuteCreate(
            from_location_id=resolved_from_location_id,
            to_location_id=resolved_to_location_id,
            transport_mode=commute_args["transport_mode"]
        )
        
        created = await repos.commutes.create_with_event(event, commute)
        
        # Build result
        result = {
            "event_id": str(created.event.id),
            "commute_id": str(created.commute.id),
            "title": title,
            "transport_mode": transport_mode,
            "from_location_id": str(resolved_from_location_id) if resolved_from_location_id else None,
            "to_location_id": str(resolved_to_location_id) if resolved_to_location_id else None,
            "message": "✅ Commute created successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
    
    except Exception as e:
        logger.error(f"Error creating commute: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating commute: {str(e)}"}, indent=2)
        )]


async def handle_update_commute(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Update commute details including transport mode, locations, event metadata, and participants.
    """
    commute_id_value = arguments.get("commute_id")
    if not commute_id_value:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "commute_id is required"}, indent=2)
        )]

    try:
        try:
            commute_id = UUID(commute_id_value)
        except ValueError:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "Invalid UUID format for commute_id"}, indent=2)
            )]
        
        # Get commute to find its event_id
        commute = await repos.commutes.get_by_id(commute_id)
        if not commute:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "Commute not found or has been deleted"}, indent=2)
            )]
        
        event_id = commute.event_id
        
        # Collect event updates
        event_updates = {}
        
        if "title" in arguments:
            event_updates["title"] = arguments["title"]
        if "notes" in arguments:
            event_updates["notes"] = arguments["notes"]
        if "start_time" in arguments:
            event_updates["start_time"] = parse_datetime(arguments["start_time"])
        if "end_time" in arguments:
            event_updates["end_time"] = parse_datetime(arguments["end_time"])
        if "tags" in arguments:
            event_updates["tags"] = arguments["tags"]

        # Reject from/to_location_name (use from/to_location_id only)
        if "from_location_name" in arguments or "to_location_name" in arguments:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameters 'from_location_name'/'to_location_name' are no longer supported. Use 'from_location_id'/'to_location_id' (UUIDs) instead. If you only have names, call search_locations/create_location first, then pass the resulting IDs."
                }, indent=2)
            )]
        
        # Handle participants update
        if "participant_ids" in arguments:
            participants = await resolve_participants(
                repos,
                participant_ids=arguments.get("participant_ids")
            )
            event_updates["participants"] = participants
        
        # Update event
        if event_updates:
            await repos.events.update(event_id, event_updates)
        
        # Collect commute updates
        commute_updates = {}
        
        if "transport_mode" in arguments:
            commute_updates["transport_mode"] = arguments["transport_mode"]
        
        # Hybrid resolution for from_location
        if "from_location_id" in arguments:
            commute_updates["from_location_id"] = UUID(arguments["from_location_id"])
        
        # Hybrid resolution for to_location
        if "to_location_id" in arguments:
            commute_updates["to_location_id"] = UUID(arguments["to_location_id"])
        
        # Update commute
        if commute_updates:
            await repos.commutes.update(commute_id, commute_updates)
        
        # Fetch and return updated commute
        updated_commute = await repos.commutes.get_by_id(commute_id)
        
        result = {
            "event_id": str(event_id),
            "commute_id": str(commute_id),
            "title": updated_commute.event_title if hasattr(updated_commute, 'event_title') else "N/A",
            "transport_mode": updated_commute.transport_mode,
            "message": "✅ Commute updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
    
    except Exception as e:
        logger.error(f"Error updating commute: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating commute: {str(e)}"}, indent=2)
        )]


async def handle_delete_commute(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete a commute by marking it as deleted"""
    event_id = arguments.get("event_id")
    
    if not event_id:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "event_id is required"}, indent=2)
        )]
    
    try:
        # Validate UUID
        try:
            event_uuid = UUID(event_id)
        except ValueError:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "Invalid UUID format for event_id"}, indent=2)
            )]
        
        async with db.pool.acquire() as conn:
            # Check if commute exists and is not already deleted
            commute = await conn.fetchrow("""
                SELECT c.id, e.title
                FROM commutes c
                JOIN events e ON c.event_id = e.id
                WHERE c.event_id = $1 AND c.is_deleted = FALSE
            """, event_uuid)
            
            if not commute:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": "Commute not found or already deleted"}, indent=2)
                )]
            
            # Soft delete the commute
            await conn.execute("""
                UPDATE commutes
                SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
                WHERE event_id = $1
            """, event_uuid)
            
            # Also mark the event as deleted
            await conn.execute("""
                UPDATE events
                SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
                WHERE id = $1
            """, event_uuid)
            
            result = {
                "event_id": event_id,
                "title": commute["title"],
                "message": "✅ Commute soft deleted successfully (can be restored with undelete_commute)"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        logger.error(f"Error deleting commute: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting commute: {str(e)}"}, indent=2)
        )]


async def handle_undelete_commute(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Restore a soft-deleted commute"""
    event_id = arguments.get("event_id")
    
    if not event_id:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "event_id is required"}, indent=2)
        )]
    
    try:
        # Validate UUID
        try:
            event_uuid = UUID(event_id)
        except ValueError:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "Invalid UUID format for event_id"}, indent=2)
            )]
        
        async with db.pool.acquire() as conn:
            # Check if commute exists and is deleted
            commute = await conn.fetchrow("""
                SELECT c.id, e.title
                FROM commutes c
                JOIN events e ON c.event_id = e.id
                WHERE c.event_id = $1 AND c.is_deleted = TRUE
            """, event_uuid)
            
            if not commute:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": "Commute not found or not deleted"}, indent=2)
                )]
            
            # Restore the commute
            await conn.execute("""
                UPDATE commutes
                SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
                WHERE event_id = $1
            """, event_uuid)
            
            # Also restore the event
            await conn.execute("""
                UPDATE events
                SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
                WHERE id = $1
            """, event_uuid)
            
            result = {
                "event_id": event_id,
                "title": commute["title"],
                "message": "✅ Commute restored successfully"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        logger.error(f"Error restoring commute: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring commute: {str(e)}"}, indent=2)
        )]
