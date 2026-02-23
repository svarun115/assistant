"""
Entity Resolution Handlers
Handles: search_exercises, search_people, search_locations, get_person_details
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID
from mcp import types

logger = logging.getLogger(__name__)


def serialize_result(obj):
    """Helper to serialize datetime and other non-JSON types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def handle_create_exercise(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Create a new custom exercise"""
    try:
        canonical_name = arguments["name"]
        category = arguments["category"]
        primary_muscle_group = arguments["primary_muscle_group"]
        secondary_muscle_groups = arguments.get("secondary_muscle_groups", [])
        equipment = arguments.get("equipment", [])
        variants = arguments.get("variants", [])
        notes = arguments.get("notes")
        
        async with db.pool.acquire() as conn:
            # Check if exercise already exists
            existing = await conn.fetchrow(
                "SELECT id, canonical_name FROM exercises WHERE canonical_name ILIKE $1",
                canonical_name
            )
            
            if existing:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Exercise already exists: {existing['canonical_name']} (ID: {existing['id']}). Use update_exercise to modify it."
                    }, indent=2)
                )]
            
            # Create the exercise
            exercise_id = await conn.fetchval("""
                INSERT INTO exercises (
                    canonical_name, category, primary_muscle_group,
                    secondary_muscle_groups, equipment, variants, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """, canonical_name, category, primary_muscle_group,
                secondary_muscle_groups, equipment, variants, notes)
            
            result = {
                "exercise_id": str(exercise_id),
                "canonical_name": canonical_name,
                "category": category,
                "primary_muscle_group": primary_muscle_group,
                "secondary_muscle_groups": secondary_muscle_groups,
                "equipment": equipment,
                "variants": variants,
                "notes": notes,
                "message": "✅ Exercise created successfully"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        logger.error(f"Error creating exercise: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating exercise: {str(e)}"}, indent=2)
        )]


async def handle_update_exercise(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update an existing exercise"""
    try:
        exercise_id = UUID(arguments["exercise_id"])
        
        # Build update fields dynamically
        updates = []
        params = []
        param_num = 1
        
        if "name" in arguments:
            updates.append(f"canonical_name = ${param_num}")
            params.append(arguments["name"])
            param_num += 1
        
        if "category" in arguments:
            updates.append(f"category = ${param_num}")
            params.append(arguments["category"])
            param_num += 1
        
        if "primary_muscle_group" in arguments:
            updates.append(f"primary_muscle_group = ${param_num}")
            params.append(arguments["primary_muscle_group"])
            param_num += 1
        
        if "secondary_muscle_groups" in arguments:
            updates.append(f"secondary_muscle_groups = ${param_num}")
            params.append(arguments["secondary_muscle_groups"])
            param_num += 1
        
        if "equipment" in arguments:
            updates.append(f"equipment = ${param_num}")
            params.append(arguments["equipment"])
            param_num += 1
        
        if "variants" in arguments:
            updates.append(f"variants = ${param_num}")
            params.append(arguments["variants"])
            param_num += 1
        
        if "notes" in arguments:
            updates.append(f"notes = ${param_num}")
            params.append(arguments["notes"])
            param_num += 1
        
        if not updates:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "No fields provided to update"}, indent=2)
            )]
        
        updates.append(f"updated_at = NOW()")
        params.append(exercise_id)
        
        async with db.pool.acquire() as conn:
            # Check if exercise exists
            existing = await conn.fetchrow(
                "SELECT id, canonical_name FROM exercises WHERE id = $1",
                exercise_id
            )
            
            if not existing:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Exercise not found: {exercise_id}"}, indent=2)
                )]
            
            # Update the exercise
            query = f"""
                UPDATE exercises
                SET {', '.join(updates)}
                WHERE id = ${param_num}
                RETURNING id, canonical_name, category, primary_muscle_group,
                          secondary_muscle_groups, equipment, variants, notes
            """
            
            updated = await conn.fetchrow(query, *params)
            
            result = {
                "exercise_id": str(updated['id']),
                "canonical_name": updated['canonical_name'],
                "category": updated['category'],
                "primary_muscle_group": updated['primary_muscle_group'],
                "secondary_muscle_groups": updated['secondary_muscle_groups'],
                "equipment": updated['equipment'],
                "variants": updated['variants'],
                "notes": updated['notes'],
                "message": "✅ Exercise updated successfully"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=serialize_result)
            )]
    
    except Exception as e:
        logger.error(f"Error updating exercise: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating exercise: {str(e)}"}, indent=2)
        )]


async def handle_create_location(arguments: dict[str, Any], repos) -> list[types.TextContent]:
    """Create a new location record"""
    try:
        from models import LocationCreate
        
        canonical_name = arguments["canonical_name"]
        place_id = arguments.get("place_id")
        location_type = arguments.get("location_type")
        notes = arguments.get("notes")
        
        # Create location
        location_create = LocationCreate(
            canonical_name=canonical_name,
            place_id=place_id,
            location_type=location_type,
            notes=notes
        )
        
        location = await repos.locations.create(location_create)
        
        result = {
            "id": str(location.id),
            "canonical_name": location.canonical_name,
            "place_id": location.place_id,
            "location_type": location.location_type,
            "notes": location.notes,
            "message": "✅ Location created successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error in create_location: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error in create_location: {str(e)}"}, indent=2)
        )]


async def handle_update_location(arguments: dict[str, Any], repos) -> list[types.TextContent]:
    """Update an existing location record"""
    try:
        location_id_str = arguments["location_id"]
        location_id = UUID(location_id_str)
        
        canonical_name = arguments.get("canonical_name")
        place_id = arguments.get("place_id")
        location_type = arguments.get("location_type")
        notes = arguments.get("notes")
        
        # Update location
        location = await repos.locations.update(
            location_id=location_id,
            canonical_name=canonical_name,
            place_id=place_id,
            location_type=location_type,
            notes=notes
        )
        
        if not location:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Location not found: {location_id}"}, indent=2)
            )]
        
        result = {
            "id": str(location.id),
            "canonical_name": location.canonical_name,
            "place_id": location.place_id,
            "location_type": location.location_type,
            "notes": location.notes,
            "message": "✅ Location updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, default=serialize_result, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error in update_location: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error in update_location: {str(e)}"}, indent=2)
        )]


async def handle_delete_location(arguments: dict[str, Any], repos) -> list[types.TextContent]:
    """Soft delete a location"""
    try:
        location_id_str = arguments["location_id"]
        location_id = UUID(location_id_str)
        
        # Soft delete the location
        await repos.locations.soft_delete(location_id)
        
        result = {
            "location_id": str(location_id),
            "message": "✅ Location deleted successfully (soft delete - can be restored with undelete_location)"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error in delete_location: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting location: {str(e)}"}, indent=2)
        )]


async def handle_undelete_location(arguments: dict[str, Any], repos) -> list[types.TextContent]:
    """Restore a deleted location"""
    try:
        location_id_str = arguments["location_id"]
        location_id = UUID(location_id_str)
        
        # Restore the location
        await repos.locations.undelete(location_id)
        
        result = {
            "location_id": str(location_id),
            "message": "✅ Location restored successfully"
        }
        
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error in undelete_location: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring location: {str(e)}"}, indent=2)
        )]


async def handle_delete_exercise(arguments: dict[str, Any], repos) -> list[types.TextContent]:
    """Soft delete an exercise"""
    try:
        exercise_id_str = arguments["exercise_id"]
        exercise_id = UUID(exercise_id_str)
        
        # Soft delete the exercise
        await repos.exercises.soft_delete(exercise_id)
        
        result = {
            "exercise_id": str(exercise_id),
            "message": "✅ Exercise deleted successfully (soft delete - can be restored with undelete_exercise)"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error in delete_exercise: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting exercise: {str(e)}"}, indent=2)
        )]


async def handle_undelete_exercise(arguments: dict[str, Any], repos) -> list[types.TextContent]:
    """Restore a deleted exercise"""
    try:
        exercise_id_str = arguments["exercise_id"]
        exercise_id = UUID(exercise_id_str)
        
        # Restore the exercise
        await repos.exercises.undelete(exercise_id)
        
        result = {
            "exercise_id": str(exercise_id),
            "message": "✅ Exercise restored successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error in undelete_exercise: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring exercise: {str(e)}"}, indent=2)
        )]



