"""
Meal Tracking MCP Tools
Specialized tools for meal tracking, nutrition, and eating patterns.
"""

from mcp import types


def _create_meal_tool() -> types.Tool:
    """Create a meal with event (event-first architecture)."""
    return types.Tool(
        name="create_meal",
        description="""Create a meal with event (event-first architecture).

HYBRID RESOLUTION:
- location_id: Uses existing location (validates existence)
- participant_ids: Uses existing people (validates existence)
- items: Provided inline (no separate IDs needed)

EXAMPLE:
{
  "event": {
    "title": "Post-workout Lunch",
    "start_time": "2025-10-12T12:30:00",
        "location_id": "<location-uuid>",
    "participant_ids": ["<person-uuid>"]
  },
  "meal": {
    "meal_title": "lunch",
    "meal_type": "home_cooked",
    "items": [
      {"item_name": "Grilled chicken breast", "quantity": "200g"},
      {"item_name": "Brown rice", "quantity": "1 cup"}
    ]
  }
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "event": {
                    "type": "object",
                    "description": "Event details (WHO, WHERE, WHEN)",
                    "properties": {
                        "title": {"type": "string", "description": "Event title"},
                        "description": {"type": "string", "description": "Event description (optional)"},
                        "start_time": {"type": "string", "description": "Start time (ISO 8601)"},
                        "end_time": {"type": "string", "description": "End time (ISO 8601, optional)"},
                        "category": {
                            "type": "string",
                            "enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
                            "description": "Event category. Default for meals: health"
                        },
                        "significance": {
                            "type": "string",
                            "enum": ["routine", "notable", "major_milestone"],
                            "default": "routine"
                        },
                        "location_id": {"type": "string", "description": "Location UUID (if known)"},
                        "participant_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Participant UUIDs (if known)"
                        },
                        "parent_event_id": {
                            "type": "string",
                            "description": "UUID of parent event for hierarchical relationships (optional). Use this to create sub-events like 'drinks during dinner party' or 'meal during trip'."
                        },
                        "notes": {"type": "string", "description": "Additional notes"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "start_time"]
                },
                "meal": {
                    "type": "object",
                    "description": "Meal details (WHAT)",
                    "properties": {
                        "meal_title": {
                            "type": "string",
                            "enum": ["breakfast", "lunch", "dinner", "snack", "brunch", "dessert"],
                            "description": "Meal type title"
                        },
                        "meal_type": {
                            "type": "string",
                            "enum": ["home_cooked", "restaurant", "takeout", "meal_prep", "fast_food", "buffet"],
                            "description": "Meal preparation type"
                        },
                        "portion_size": {
                            "type": "string",
                            "enum": ["small", "medium", "large", "extra_large"],
                            "description": "Portion size"
                        },
                        "context": {
                            "type": "string",
                            "enum": ["pre_workout", "post_workout", "celebration", "business", "date", "casual"],
                            "description": "Meal context"
                        },
                        "items": {
                            "type": "array",
                            "description": "Food items in the meal",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "item_name": {"type": "string", "description": "Food item name"},
                                    "quantity": {"type": "string", "description": "Quantity (e.g., '200g', '1 cup')"}
                                },
                                "required": ["item_name"]
                            }
                        },
                        "preparation_method": {"type": "string", "description": "How meal was prepared"},
                        "cuisine": {"type": "string", "description": "Cuisine type (e.g., 'Italian', 'Indian')"}
                    },
                    "required": ["meal_title"]
                }
            },
            "required": ["event", "meal"]
        }
    )


def _update_meal_tool() -> types.Tool:
    return types.Tool(
        name="update_meal",
        description="""Update an existing meal. Can update meal metadata (meal_type, portion_size), food items, and event-level fields like participants.

Note: To update items, provide the complete new items list (it replaces existing items).

EXAMPLE - Update meal items:
{
  "meal_id": "uuid-of-meal",
  "meal_type": "restaurant",
  "items": [
    {"item_name": "Grilled salmon", "quantity": "250g"}
  ]
}

EXAMPLE - Update participants:
{
  "meal_id": "uuid-of-meal",
  "participant_ids": ["<uuid-1>", "<uuid-2>"]
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "meal_id": {
                    "type": "string",
                    "description": "UUID of the meal to update (required)"
                },
                "meal_type": {
                    "type": "string",
                    "enum": ["home_cooked", "restaurant", "takeout", "delivered", "meal_prep"],
                    "description": "Updated meal type (optional)"
                },
                "portion_size": {
                    "type": "string",
                    "enum": ["small", "medium", "large", "extra_large"],
                    "description": "Updated portion size (optional)"
                },
                "context": {
                    "type": "string",
                    "enum": ["pre_workout", "post_workout", "celebration", "business", "date", "casual"],
                    "description": "Updated meal context (optional)"
                },
                "cuisine": {
                    "type": "string",
                    "description": "Updated cuisine type (optional)"
                },
                "preparation_method": {
                    "type": "string",
                    "description": "Updated preparation method (optional)"
                },
                "items": {
                    "type": "array",
                    "description": "Complete list of food items (replaces existing items)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_name": {"type": "string"},
                            "quantity": {"type": "string"}
                        },
                        "required": ["item_name"]
                    }
                },
                "participant_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Updated list of participant UUIDs for the meal event (replaces existing participants)"
                }
            },
            "required": ["meal_id"]
        }
    )


def get_meal_tools() -> list[types.Tool]:
    """
    Returns only creation/write tools for meals.

    Tools included:
    - create_meal: Create a meal with event and items
    - update_meal: Update meal metadata and items

    Delete/restore: use delete_entity / restore_entity with entity_type="meal".
    For querying/analyzing meals, use execute_sql_query instead (SQL-first architecture).
    """
    return [
        _create_meal_tool(),
        _update_meal_tool(),
    ]


