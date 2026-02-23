"""
Meal Handlers
Handles: create_meal, update_meal, delete_meal, undelete_meal
All meal reads use execute_sql_query (SQL-first architecture).
"""

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from mcp import types

from models import (
    EventCreate, EventType, EventParticipant, Significance,
    MealCreate, MealItem,
)


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
            return location.id
        except ValueError as e:
            raise ValueError(f"Invalid location_id: {e}")
    return None


async def resolve_participants(
    repos,
    participant_ids: list[str] = None,
    role: str = "participant"
) -> list[EventParticipant]:
    """
    Resolve participant_ids to EventParticipant objects.
    
    Only accepts participant_ids (UUIDs). People must be created separately.
    """
    participants = []
    
    if participant_ids:
        for person_id_str in participant_ids:
            person_id = UUID(person_id_str)
            person = await repos.people.get_by_id(person_id)
            if not person:
                raise ValueError(f"Person not found: {person_id_str}")
            participants.append(EventParticipant(person_id=person_id, person_name=person.canonical_name, role=role))
    
    return participants


async def handle_create_meal(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Create a meal with event (event-first pattern) with hybrid resolution"""
    try:
        event_data = arguments["event"]
        meal_data = arguments["meal"]
        
        # Reject participant_names parameter (use participant_ids only)
        if "participant_names" in event_data:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'participant_names' is no longer supported. Use 'participant_ids' with UUIDs instead. Create people first using create_person tool if needed."
                }, indent=2)
            )]

        # Reject location_name parameter (use location_id only)
        if "location_name" in event_data:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'location_name' is no longer supported. Use 'location_id' (UUID) instead. If you only have a name, call search_locations/create_location first, then pass the resulting location_id."
                }, indent=2)
            )]
        
        # Resolve location
        location_id = await resolve_location(
            repos,
            location_id=event_data.get("location_id")
        )
        
        # Resolve participants
        participants = await resolve_participants(
            repos,
            participant_ids=event_data.get("participant_ids")
        )
        
        # Parse timestamps
        start_time = datetime.fromisoformat(event_data["start_time"])
        end_time = None
        if event_data.get("end_time"):
            end_time = datetime.fromisoformat(event_data["end_time"])
        
        # Validate parent_event_id if provided
        parent_event_id = None
        if event_data.get("parent_event_id"):
            try:
                parent_uuid = UUID(event_data["parent_event_id"])
                parent = await repos.events.get_by_id(parent_uuid)
                if not parent:
                    return [types.TextContent(
                        type="text",
                        text=json.dumps({"error": f"Parent event not found: {parent_uuid}"}, indent=2)
                    )]
                parent_event_id = parent_uuid
            except ValueError as e:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Invalid parent_event_id format: {e}"}, indent=2)
                )]
        
        # Create event
        event = EventCreate(
            event_type=EventType.MEAL,
            title=event_data["title"],
            description=event_data.get("description"),
            start_time=start_time,
            end_time=end_time,
            location_id=location_id,
            parent_event_id=parent_event_id,
            category=event_data.get("category", "social"),
            significance=Significance(event_data.get("significance", "routine")),
            participants=participants,
            notes=event_data.get("notes"),
            tags=event_data.get("tags", [])
        )
        
        # Process meal items
        items = []
        for item_data in meal_data.get("items", []):
            items.append(MealItem(
                item_name=item_data["item_name"],
                quantity=item_data.get("quantity")
            ))
        
        # Create meal
        meal = MealCreate(
            meal_title=meal_data.get("meal_title"),
            meal_type=meal_data.get("meal_type"),
            portion_size=meal_data.get("portion_size"),
            items=items
        )
        
        # Create meal with event
        created = await repos.meals.create_with_event(event, meal)
        
        result = {
            "event_id": str(created.event.id),
            "meal_id": str(created.meal.id),
            "title": created.event.title,
            "start_time": created.event.start_time.isoformat(),
            "meal_type": created.meal.meal_type,
            "message": "✅ Meal created successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
        
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating meal: {str(e)}"}, indent=2)
        )]


async def handle_update_meal(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Update an existing meal. Can update meal fields, items, and event participants."""
    try:
        meal_id = UUID(arguments["meal_id"])
        
        # Get meal to find its event_id
        meal = await repos.meals.get_by_id(meal_id)
        if not meal:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "Meal not found"}, indent=2)
            )]
        
        event_id = meal.event_id
        updates = {}
        
        # Collect meal-specific updates
        if "meal_title" in arguments:
            updates["meal_title"] = arguments["meal_title"]
        if "meal_type" in arguments:
            updates["meal_type"] = arguments["meal_type"]
        if "portion_size" in arguments:
            updates["portion_size"] = arguments["portion_size"]
        if "context" in arguments:
            updates["context"] = arguments["context"]
        if "cuisine" in arguments:
            updates["cuisine"] = arguments["cuisine"]
        if "preparation_method" in arguments:
            updates["preparation_method"] = arguments["preparation_method"]
        
        # Check if anything to update
        has_meal_updates = bool(updates)
        has_item_updates = "items" in arguments
        has_participant_updates = "participant_ids" in arguments
        
        if not has_meal_updates and not has_item_updates and not has_participant_updates:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "No updates provided"}, indent=2)
            )]
        
        # Update meal
        if has_meal_updates:
            updated = await repos.meals.update(meal_id, updates)
        
        # Handle items if provided
        if has_item_updates:
            # Clear existing items
            delete_query = """
                DELETE FROM meal_items 
                WHERE meal_id = $1
            """
            async with db.pool.acquire() as conn:
                await conn.execute(delete_query, meal_id)
            
            # Add new items
            for item in arguments.get("items", []):
                item_insert_query = """
                    INSERT INTO meal_items (meal_id, item_name, quantity)
                    VALUES ($1, $2, $3)
                """
                async with db.pool.acquire() as conn:
                    await conn.execute(
                        item_insert_query,
                        meal_id,
                        item.get("item_name"),
                        item.get("quantity")
                    )
        
        # Handle participants update if provided
        if has_participant_updates:
            participants = await resolve_participants(
                repos,
                participant_ids=arguments.get("participant_ids")
            )
            
            event_updates = {"participants": participants}
            await repos.events.update(event_id, event_updates)
        
        result = {
            "meal_id": str(meal_id),
            "event_id": str(event_id),
            "message": "✅ Meal updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
        
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating meal: {str(e)}"}, indent=2)
        )]


async def handle_delete_meal(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Soft delete a meal"""
    try:
        meal_id = UUID(arguments["meal_id"])
        
        query = """
            UPDATE meals 
            SET is_deleted = true, deleted_at = NOW()
            WHERE id = $1
            RETURNING id, meal_title
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, meal_id)
            
            if not row:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Meal with ID {meal_id} not found"}, indent=2)
                )]
            
            result = {
                "meal_id": str(row['id']),
                "title": row['meal_title'],
                "message": "✅ Meal deleted successfully (soft delete)"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting meal: {str(e)}"}, indent=2)
        )]


async def handle_undelete_meal(
    db,
    repos,
    arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Restore a deleted meal"""
    try:
        meal_id = UUID(arguments["meal_id"])
        
        query = """
            UPDATE meals 
            SET is_deleted = false, deleted_at = NULL
            WHERE id = $1
            RETURNING id, meal_title
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, meal_id)
            
            if not row:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Meal with ID {meal_id} not found"}, indent=2)
                )]
            
            result = {
                "meal_id": str(row['id']),
                "title": row['meal_title'],
                "message": "✅ Meal restored successfully"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring meal: {str(e)}"}, indent=2)
        )]
