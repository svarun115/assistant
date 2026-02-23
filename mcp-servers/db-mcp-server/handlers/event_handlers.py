"""
Event Handlers - Unified Event Type System
Handles: create_event, update_event, delete_event, undelete_event

Supports all event types:
- "sleep" - Sleep events with quality tracking (replaces create_sleep_event)
- "reflection" - Reflection events with mood tracking (replaces create_reflection)  
- "work" - Work events with productivity tracking (replaces create_work_block)
- "generic" - Generic events with no special handling

All event reads use execute_sql_query (SQL-first architecture).
Consolidation saves ~725 lines of duplicate code (sleep_handlers.py, reflection_handlers.py, work_handlers.py).
"""

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from mcp import types

from models import EventCreate, EventType, EventParticipant, Significance, ReflectionCreate

logger_name = "event_handlers"


def serialize_result(obj):
    """Helper to serialize datetime and other non-JSON types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


# ============================================================================
# Type-specific helper functions - support sleep, reflection, work consolidation
# ============================================================================

def _build_notes_for_type(event_type: str, arguments: dict[str, Any]) -> str:
    """Build notes based on event type-specific fields"""
    notes_parts = []
    
    if arguments.get("notes"):
        notes_parts.append(arguments["notes"])
    
    if event_type == "sleep":
        if arguments.get("quality"):
            notes_parts.append(f"Quality: {arguments['quality']}")
        if arguments.get("interruptions") is not None:
            notes_parts.append(f"Interruptions: {arguments['interruptions']}")
        if arguments.get("dream_recall") is not None:
            notes_parts.append(f"Dream recall: {'Yes' if arguments['dream_recall'] else 'No'}")
    
    elif event_type == "reflection":
        if arguments.get("mood"):
            notes_parts.append(f"Mood: {arguments['mood']}")
        if arguments.get("prompt_question"):
            notes_parts.append(f"Prompt: {arguments['prompt_question']}")
    
    elif event_type == "work":
        if arguments.get("work_type"):
            notes_parts.append(f"Work type: {arguments['work_type']}")
        if arguments.get("work_context"):
            notes_parts.append(f"Context: {arguments['work_context']}")
        if arguments.get("productivity"):
            notes_parts.append(f"Productivity: {arguments['productivity']}")
    
    return " | ".join(notes_parts) if notes_parts else None


def _get_default_title(event_type: str, arguments: dict[str, Any]) -> str:
    """Get default title based on event type"""
    try:
        if event_type == "sleep":
            start_time = datetime.fromisoformat(arguments["start_time"])
            end_time = datetime.fromisoformat(arguments.get("end_time", arguments["start_time"]))
            duration_hours = (end_time - start_time).total_seconds() / 3600
            return f"Sleep ({duration_hours:.1f}h)"
        elif event_type == "reflection":
            return arguments.get("title", "Reflection")
        elif event_type == "work":
            return arguments.get("title", "Work Block")
        else:
            return arguments.get("title", "Event")
    except Exception:
        return arguments.get("title", "Event")


def _build_tags_for_work(arguments: dict[str, Any]) -> list[str]:
    """Build tags from work event attributes"""
    tags = arguments.get("tags", []).copy() if isinstance(arguments.get("tags"), list) else []
    
    if arguments.get("work_type") and arguments["work_type"] not in tags:
        tags.append(arguments["work_type"])
    if arguments.get("work_context") and arguments["work_context"] not in tags:
        tags.append(arguments["work_context"])
    if arguments.get("productivity") and arguments["productivity"] not in tags:
        tags.append(arguments["productivity"])
    if arguments.get("additional_tags"):
        tags.extend([t for t in arguments["additional_tags"] if t not in tags])
    
    return tags


async def _create_reflection_metadata(
    repos,
    event_id: UUID,
    arguments: dict[str, Any]
) -> Any:
    """Create reflection-specific metadata if reflection event"""
    reflection_create = ReflectionCreate(
        event_id=event_id,
        reflection_type=arguments.get("reflection_type"),
        mood=arguments.get("mood"),
        mood_score=arguments.get("mood_score"),
        prompt_question=arguments.get("prompt_question"),
        key_insights=arguments.get("key_insights"),
        action_items=arguments.get("action_items")
    )
    
    return await repos.reflections.create(reflection_create)


async def resolve_location(
    repos,
    location_id: Optional[str] = None
) -> Optional[UUID]:
    """Resolve location_id to UUID (no auto-create by name)."""
    if location_id:
        try:
            location_uuid = UUID(location_id)
            location = await repos.locations.get_by_id(location_uuid)
            if not location:
                raise ValueError(f"Location with ID {location_id} not found")
            return location.id
        except ValueError as e:
            raise ValueError(f"Invalid location_id format: {e}")
    return None


async def resolve_participants(
    repos,
    participant_ids: list[str] = None,
    role: str = "participant",
    interaction_mode: str = None
) -> list[EventParticipant]:
    """Resolve participant_ids to EventParticipant objects.
    
    Only accepts participant_ids (UUIDs). People must be created separately.
    """
    participants = []
    
    if participant_ids:
        for person_id_str in participant_ids:
            try:
                person_uuid = UUID(person_id_str)
                person = await repos.people.get_by_id(person_uuid)
                if not person:
                    raise ValueError(f"Person with ID {person_id_str} not found")
                participants.append(EventParticipant(
                    person_id=person.id, 
                    role=role,
                    interaction_mode=interaction_mode
                ))
            except ValueError as e:
                raise ValueError(f"Invalid participant_id format: {e}")
    
    return participants


async def handle_create_event(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Create a new event - supports all types (sleep, reflection, work, generic)
    
    Type-specific behavior:
    - sleep: Calculates duration, tracks quality/interruptions/dream_recall
    - reflection: Creates reflection metadata with mood/insights
    - work: Handles participants, tracks productivity/work_type/context
    - generic: Standard event with no special handling
    """
    try:
        # Reject participant_names parameter (use participant_ids only)
        if "participant_names" in arguments:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'participant_names' is no longer supported. Use 'participant_ids' with UUIDs instead. Create people first using create_person tool if needed."
                }, indent=2)
            )]

        # Reject location_name parameter (use location_id only)
        if "location_name" in arguments:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'location_name' is no longer supported. Use 'location_id' (UUID) instead. If you only have a name, call search_locations/create_location first, then pass the resulting location_id."
                }, indent=2)
            )]
        
        # Determine event type - default to generic if not specified
        event_type = arguments.get("event_type", "generic")
        
        # Validate event type
        valid_types = ["sleep", "reflection", "work", "generic"]
        if event_type not in valid_types:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Invalid event_type '{event_type}'. Must be one of: {', '.join(valid_types)}"
                }, indent=2)
            )]
        
        # Resolve location
        location_id = await resolve_location(
            repos,
            location_id=arguments.get("location_id")
        )
        
        # Resolve participants (mainly for work events)
        participants = []
        interaction_mode = arguments.get("interaction_mode")
        
        if event_type == "work":
            participants = await resolve_participants(
                repos,
                participant_ids=arguments.get("participant_ids"),
                interaction_mode=interaction_mode
            )
        else:
            participants = await resolve_participants(
                repos,
                participant_ids=arguments.get("participant_ids"),
                interaction_mode=interaction_mode
            )
        
        # Parse timestamps
        start_time = datetime.fromisoformat(arguments["start_time"])
        end_time = None
        if arguments.get("end_time"):
            end_time = datetime.fromisoformat(arguments["end_time"])
        
        # Build type-specific attributes
        title = _get_default_title(event_type, arguments)
        notes = _build_notes_for_type(event_type, arguments)
        tags = _build_tags_for_work(arguments) if event_type == "work" else arguments.get("tags", [])
        
        # Determine category based on event type
        category = arguments.get("category")
        if not category:
            if event_type == "sleep":
                category = "health"
            elif event_type == "reflection":
                category = "personal"
            elif event_type == "work":
                category = "work"
            else:
                category = "social"
        
        # Parse parent_event_id if provided
        parent_event_id = None
        if arguments.get("parent_event_id"):
            parent_event_id = UUID(arguments["parent_event_id"])
        
        # Parse and validate source_person_id if provided
        source_person_id = None
        if arguments.get("source_person_id"):
            source_person_uuid = UUID(arguments["source_person_id"])
            # Validate the person exists
            source_person = await repos.people.get_by_id(source_person_uuid)
            if not source_person:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Source person with ID {arguments['source_person_id']} not found"
                    }, indent=2)
                )]
            source_person_id = source_person_uuid
        
        # Create event
        event = EventCreate(
            event_type=EventType(event_type),
            title=title,
            description=arguments.get("description"),
            start_time=start_time,
            end_time=end_time,
            location_id=location_id,
            parent_event_id=parent_event_id,
            source_person_id=source_person_id,
            category=category,
            significance=Significance(arguments.get("significance", "routine")),
            participants=participants,
            notes=notes,
            tags=tags
        )
        
        # Create base event
        created = await repos.events.create(event)
        
        # Handle type-specific metadata
        response_data = {
            "event_id": str(created.id),
            "event_type": event_type,
            "title": created.title,
            "start_time": created.start_time.isoformat(),
        }
        
        if end_time:
            response_data["end_time"] = created.end_time.isoformat()
            if event_type == "sleep":
                duration_hours = (end_time - start_time).total_seconds() / 3600
                response_data["duration_hours"] = round(duration_hours, 1)
                response_data["quality"] = arguments.get("quality")
        
        # Create reflection metadata if reflection event
        if event_type == "reflection":
            try:
                reflection = await _create_reflection_metadata(repos, created.id, arguments)
                response_data["reflection_id"] = str(reflection.id)
                response_data["mood"] = arguments.get("mood")
                response_data["mood_score"] = arguments.get("mood_score")
            except Exception as e:
                # Reflection metadata is optional - log but don't fail
                response_data["warning"] = f"Event created but reflection metadata failed: {str(e)}"
        
        response_data["message"] = f"✅ {event_type.capitalize()} event created successfully"
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response_data, default=serialize_result, indent=2)
        )]
        
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating event: {str(e)}"}, indent=2)
        )]


async def handle_update_event(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update existing event - supports all types (sleep, reflection, work, generic)
    
    Type-specific behavior:
    - sleep: Updates quality/interruptions/dream_recall in notes
    - reflection: Updates reflection metadata (mood/insights/action_items)
    - work: Updates work-specific tags (work_type/work_context/productivity)
    - generic: Standard event fields
    """
    try:
        # Reject participant_names parameter (use participant_ids only)
        if "participant_names" in arguments:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'participant_names' is no longer supported. Use 'participant_ids' with UUIDs instead."
                }, indent=2)
            )]

        # Reject location_name parameter (use location_id only)
        if "location_name" in arguments:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'location_name' is no longer supported. Use 'location_id' (UUID) instead. If you only have a name, call search_locations/create_location first, then pass the resulting location_id."
                }, indent=2)
            )]
        
        event_id = UUID(arguments["event_id"])
        event_type = arguments.get("event_type")
        
        # Get current event to verify it exists and determine type if not provided
        current_event = await repos.events.get_by_id(event_id)
        if not current_event:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Event {event_id} not found"}, indent=2)
            )]
        
        # Use provided event_type or detect from current event
        if not event_type:
            event_type = str(current_event.event_type) if current_event.event_type else "generic"
        else:
            # Verify type matches if provided
            if current_event.event_type and str(current_event.event_type) != event_type:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Event type mismatch: event is {current_event.event_type}, you specified {event_type}"
                    }, indent=2)
                )]
        
        updates = {}
        
        # Collect standard updates
        if "title" in arguments:
            updates["title"] = arguments["title"]
        if "description" in arguments:
            updates["description"] = arguments["description"]
        if "start_time" in arguments:
            updates["start_time"] = datetime.fromisoformat(arguments["start_time"]) if arguments["start_time"] is not None else None
        if "end_time" in arguments:
            updates["end_time"] = datetime.fromisoformat(arguments["end_time"]) if arguments["end_time"] is not None else None
        if "notes" in arguments:
            updates["notes"] = arguments["notes"]
        if "category" in arguments:
            updates["category"] = arguments["category"]
        if "significance" in arguments:
            updates["significance"] = arguments["significance"]
        if "tags" in arguments:
            updates["tags"] = arguments["tags"]
        if "parent_event_id" in arguments:
            if arguments["parent_event_id"] is None:
                updates["parent_event_id"] = None
            else:
                updates["parent_event_id"] = UUID(arguments["parent_event_id"])
        
        # Handle source_person_id update
        if "source_person_id" in arguments:
            if arguments["source_person_id"] is None:
                updates["source_person_id"] = None
            else:
                source_person_uuid = UUID(arguments["source_person_id"])
                # Validate the person exists
                source_person = await repos.people.get_by_id(source_person_uuid)
                if not source_person:
                    return [types.TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"Source person with ID {arguments['source_person_id']} not found"
                        }, indent=2)
                    )]
                updates["source_person_id"] = source_person_uuid
        
        # Handle external system references
        if "external_event_id" in arguments:
            updates["external_event_id"] = arguments["external_event_id"]
        if "external_event_source" in arguments:
            updates["external_event_source"] = arguments["external_event_source"]
        
        # Handle location update
        if "location_id" in arguments:
            location_id = await resolve_location(
                repos,
                location_id=arguments.get("location_id")
            )
            updates["location_id"] = location_id
        
        # Handle participants update
        if "participant_ids" in arguments:
            participants = await resolve_participants(
                repos,
                participant_ids=arguments.get("participant_ids"),
                interaction_mode=arguments.get("interaction_mode")
            )
            updates["participants"] = participants
        elif "interaction_mode" in arguments:
            # Update interaction_mode for existing participants
            current_participants = current_event.participants
            updated_participants = []
            for p in current_participants:
                updated_participants.append(EventParticipant(
                    person_id=p.person_id,
                    role=p.role,
                    interaction_mode=arguments["interaction_mode"]
                ))
            if updated_participants:
                updates["participants"] = updated_participants
        
        metadata_updated = False
        
        # Handle type-specific note updates
        if event_type == "sleep" and any(k in arguments for k in ["quality", "interruptions", "dream_recall", "notes"]):
            notes = _build_notes_for_type("sleep", arguments)
            if notes:
                updates["notes"] = notes
        
        elif event_type == "reflection" and any(k in arguments for k in ["mood", "mood_score", "prompt_question", "key_insights", "action_items", "reflection_type", "notes"]):
            # For reflection, also update reflection metadata
            reflection_updates = {}
            if "mood" in arguments:
                reflection_updates["mood"] = arguments["mood"]
            if "mood_score" in arguments:
                reflection_updates["mood_score"] = arguments["mood_score"]
            if "prompt_question" in arguments:
                reflection_updates["prompt_question"] = arguments["prompt_question"]
            if "key_insights" in arguments:
                reflection_updates["key_insights"] = arguments["key_insights"]
            if "action_items" in arguments:
                reflection_updates["action_items"] = arguments["action_items"]
            if "reflection_type" in arguments:
                reflection_updates["reflection_type"] = arguments["reflection_type"]
            
            # Update reflection metadata if provided
            if reflection_updates:
                try:
                    await repos.reflections.update(event_id, reflection_updates)
                    metadata_updated = True
                except Exception as e:
                    return [types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Error updating reflection metadata: {str(e)}"}, indent=2)
                    )]
            
            # Update event notes
            notes = _build_notes_for_type("reflection", arguments)
            if notes:
                updates["notes"] = notes
        
        elif event_type == "work" and any(k in arguments for k in ["work_type", "work_context", "productivity"]):
            # Rebuild tags with updated work attributes
            tags = _build_tags_for_work(arguments)
            if tags:
                updates["tags"] = tags
        
        if not updates and not metadata_updated:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "No updates provided"}, indent=2)
            )]
        
        # Perform update
        if updates:
            updated = await repos.events.update(event_id, updates)
        else:
            updated = current_event
        
        result = {
            "event_id": str(updated.id),
            "event_type": event_type,
            "title": updated.title,
            "message": f"✅ {event_type.capitalize()} event updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
        
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating event: {str(e)}"}, indent=2)
        )]


async def handle_delete_event(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete an event"""
    try:
        event_id = UUID(arguments["event_id"])
        
        query = """
            UPDATE events 
            SET is_deleted = true, deleted_at = NOW()
            WHERE id = $1
            RETURNING id, title, start_time
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, event_id)
            
            if not row:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Event with ID {event_id} not found"}, indent=2)
                )]
            
            result = {
                "event_id": str(row['id']),
                "title": row['title'],
                "start_time": row['start_time'].isoformat(),
                "message": "✅ Event deleted successfully (soft delete)"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, default=serialize_result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting event: {str(e)}"}, indent=2)
        )]


async def handle_undelete_event(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Restore a deleted event"""
    try:
        event_id = UUID(arguments["event_id"])
        
        query = """
            UPDATE events 
            SET is_deleted = false, deleted_at = NULL
            WHERE id = $1
            RETURNING id, title, start_time
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, event_id)
            
            if not row:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Event with ID {event_id} not found"}, indent=2)
                )]
            
            result = {
                "event_id": str(row['id']),
                "title": row['title'],
                "start_time": row['start_time'].isoformat(),
                "message": "✅ Event restored successfully"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, default=serialize_result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring event: {str(e)}"}, indent=2)
        )]



