"""
Location Management MCP Tools
Domain-specific tools for managing locations and venue data.
"""

from mcp import types


def get_location_tools() -> list[types.Tool]:
    """
    Returns location management write tools.

    Tools included:
    - create_location: Create a new location record
    - update_location: Update an existing location record

    For delete/restore: use delete_entity / restore_entity with entity_type="location".
    For checking dependencies before deletion or searching locations, use execute_sql_query instead (SQL-first architecture).
    Example: SELECT * FROM events WHERE location_id = '<location_id>'
    """
    return [
        _create_location_tool(),
        _update_location_tool(),
    ]


# Individual tool definitions
def _create_location_tool() -> types.Tool:
    return types.Tool(
        name="create_location",
        description="Create a new location record. Use search_locations first to avoid duplicates. Returns the created location with generated UUID.\n\nIMPORTANT: Always call search_places() from Google Places tools first to find the place_id for public venues (gyms, restaurants, parks, offices, etc.). Only skip place_id for private residences or informal locations (e.g., 'home', 'Sarah's backyard'). Having a place_id ensures rich metadata (address, hours, phone) is available.",
        inputSchema={
            "type": "object",
            "properties": {
                "canonical_name": {
                    "type": "string",
                    "description": "Primary name for the location (required)"
                },
                "place_id": {
                    "type": "string",
                    "description": "Google Place ID for API integration. STRONGLY RECOMMENDED for public venues - call search_places() first to find this. Only optional for private/informal locations."
                },
                "location_type": {
                    "type": "string",
                    "description": "Type of location (e.g., 'gym', 'restaurant', 'park', 'residence', 'workplace') (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional context about the location (optional)"
                }
            },
            "required": ["canonical_name"]
        }
    )


def _update_location_tool() -> types.Tool:
    return types.Tool(
        name="update_location",
        description="Update an existing location record. Only provided fields will be updated. Returns the updated location object.",
        inputSchema={
            "type": "object",
            "properties": {
                "location_id": {
                    "type": "string",
                    "description": "UUID of the location to update (required)"
                },
                "canonical_name": {
                    "type": "string",
                    "description": "Update the location name (optional)"
                },
                "place_id": {
                    "type": "string",
                    "description": "Update Google Place ID (optional)"
                },
                "location_type": {
                    "type": "string",
                    "description": "Update location type (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Update notes (optional)"
                }
            },
            "required": ["location_id"]
        }
    )


