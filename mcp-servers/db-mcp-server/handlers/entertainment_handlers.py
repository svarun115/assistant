"""
Entertainment Handlers
Handles entertainment logging (movies, TV shows, videos, podcasts, live performances, gaming, reading)
"""

import json
from typing import Any, Dict
from uuid import UUID
from mcp import types
from models import EventCreate, EntertainmentCreate


async def handle_create_entertainment(db: Any, repos: Any, arguments: Dict[str, Any]) -> list[types.TextContent]:
    """
    Create entertainment with event (event-first architecture).
    
    Entertainment system replaces the old media system with richer functionality:
    - Event-based: All entertainment tied to events (captures when, where, with whom)
    - Rich metadata: Tracks show details, episodes, channels, venues, etc.
    - Flexible: Supports movies, TV, videos, podcasts, live performances, gaming, reading
    
    Args:
        db: Database connection
        repos: Repository container
        arguments: Tool arguments containing event and entertainment data
    
    Returns:
        List of TextContent with created entertainment and event data
    """
    try:
        event_data = arguments.get("event", {})
        entertainment_data = arguments.get("entertainment", {})

        # Reject location_name parameter (use location_id only)
        if "location_name" in event_data:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Parameter 'location_name' is no longer supported. Use 'location_id' (UUID) instead. If you only have a name, call search_locations/create_location first, then pass the resulting location_id."
                }, indent=2)
            )]
        
        # Parse event data
        event = EventCreate(**event_data)
        
        # Parse entertainment data
        entertainment = EntertainmentCreate(**entertainment_data)
        
        # Create entertainment with event
        result = await repos.entertainment.create_with_event(
            event=event,
            entertainment=entertainment
        )
        
        response = {
            "status": "success",
            "entertainment_id": str(result.entertainment.id),
            "event_id": str(result.event.id),
            "entertainment_type": result.entertainment.entertainment_type,
            "title": result.entertainment.title,
            "event_title": result.event.title,
            "start_time": result.event.start_time.isoformat() if result.event.start_time else None,
            "personal_rating": result.entertainment.personal_rating,
            "completion_status": result.entertainment.completion_status,
            "message": "✅ Entertainment logged"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2)
        )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating entertainment: {str(e)}"}, indent=2)
        )]
