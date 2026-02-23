"""
Travel & Commute MCP Tools
Specialized tools for tracking commutes, travel patterns, and transportation expenses.
"""

from mcp import types


def get_travel_tools() -> list[types.Tool]:
    """
    Returns travel/commute write tools (CRUD operations).

    Tools included:
    - create_commute: Create a commute/travel record
    - update_commute: Update commute details

    Delete/restore: use delete_entity / restore_entity with entity_type="commute".
    For querying/analyzing commute history, use execute_sql_query instead.
    """
    return [
        _create_commute_tool(),
        _update_commute_tool(),
    ]


def _create_commute_tool() -> types.Tool:
    """Create a commute/travel record with event-first architecture"""
    return types.Tool(
        name="create_commute",
        description="""Create a commute with event (event-first architecture).

DEPENDENCY CHAIN:
1. Location: Auto-resolved via names OR validated via IDs
2. People: Auto-created via names OR validated via IDs

HYBRID RESOLUTION:
- from_location_id: Uses existing location (validates existence)
- to_location_id: Uses existing location (validates existence)
- participant_ids: Uses existing people (validates existence)

EXAMPLE:
{
  "event": {
    "title": "Morning Commute to Office",
    "start_time": "2025-10-27T08:30:00",
    "end_time": "2025-10-27T09:15:00"
  },
  "commute": {
        "from_location_id": "<location-uuid-home>",
        "to_location_id": "<location-uuid-office>",
    "transport_mode": "driving"
  }
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "event": {
                    "type": "object",
                    "description": "Event details (WHO, WHERE, WHEN)",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Event title"
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start time (ISO 8601: YYYY-MM-DDTHH:MM:SS)"
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End time (ISO 8601, optional)"
                        },
                        "participant_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Participant UUIDs (if known)"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Additional notes"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "category": {
                            "type": "string",
                            "enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
                            "description": "Event category. Default for commutes: travel"
                        },
                        "significance": {
                            "type": "string",
                            "enum": ["routine", "notable", "major_milestone"],
                            "default": "routine"
                        }
                    },
                    "required": ["title", "start_time"]
                },
                "commute": {
                    "type": "object",
                    "description": "Commute details (WHAT)",
                    "properties": {
                        "from_location_id": {
                            "type": "string",
                            "description": "Origin location UUID (if known)"
                        },
                        "to_location_id": {
                            "type": "string",
                            "description": "Destination location UUID (if known)"
                        },
                        "transport_mode": {
                            "type": "string",
                            "enum": [
                                "driving", "public_transit", "walking", "cycling",
                                "running", "flying", "rideshare", "taxi", "train",
                                "bus", "subway", "ferry", "scooter", "other"
                            ],
                            "description": "Transport mode"
                        }
                    },
                    "required": ["transport_mode"]
                }
            },
            "required": ["event", "commute"]
        }
    )


def _update_commute_tool() -> types.Tool:
    """Update an existing commute record"""
    return types.Tool(
        name="update_commute",
        description="""Update commute details including transport mode, locations, event metadata, or participants.

Updates can modify:
- Transport mode
- Origin/destination locations
- Event details (title, notes, times)
- Participants

EXAMPLE - Update transport mode:
{
  "commute_id": "uuid-here",
  "transport_mode": "public_transit",
  "notes": "Took the express bus today"
}

EXAMPLE - Update participants:
{
  "commute_id": "uuid-here",
  "participant_ids": ["<uuid-1>", "<uuid-2>"]
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "commute_id": {
                    "type": "string",
                    "description": "UUID of the commute to update (required)"
                },
                "transport_mode": {
                    "type": "string",
                    "enum": [
                        "driving", "public_transit", "walking", "cycling",
                        "running", "flying", "rideshare", "taxi", "train",
                        "bus", "subway", "ferry", "scooter", "other"
                    ],
                    "description": "Update transport mode (optional)"
                },
                "from_location_id": {
                    "type": "string",
                    "description": "Update origin location UUID (optional)"
                },
                "to_location_id": {
                    "type": "string",
                    "description": "Update destination location UUID (optional)"
                },
                "title": {
                    "type": "string",
                    "description": "Update event title (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Update event notes (optional)"
                },
                "start_time": {
                    "type": "string",
                    "description": "Update start time (ISO 8601, optional)"
                },
                "end_time": {
                    "type": "string",
                    "description": "Update end time (ISO 8601, optional)"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Update tags (optional)"
                },
                "participant_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Updated list of participant UUIDs for the commute event (replaces existing participants, optional)"
                }
            },
            "required": ["commute_id"]
        }
    )


