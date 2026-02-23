"""
Planning Tools - MCP tools for daily plan tracking

Provides:
- create_daily_plan: Create a daily plan with timeline items
- update_plan_item: Update the status of a planned item
- get_plan_vs_actual: Get plan vs. actual comparison for a date
- get_planning_insights: Analytics over a date range
"""

from mcp import types


def _create_daily_plan_tool() -> types.Tool:
    return types.Tool(
        name="create_daily_plan",
        description=(
            "Create a daily plan with timeline items. Called when a day's plan is approved. "
            "Auto-increments version for the same date (first plan is v1, revisions are v2+). "
            "Returns plan_id and item_ids for later status updates via update_plan_item."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "plan_date": {
                    "type": "string",
                    "description": "Date of the plan (YYYY-MM-DD)"
                },
                "source": {
                    "type": "string",
                    "description": "Source of the plan",
                    "default": "daily_tracker"
                },
                "time_budget": {
                    "type": "object",
                    "description": "Planned time budget in minutes by category",
                    "properties": {
                        "work": {"type": "integer"},
                        "personal": {"type": "integer"},
                        "health": {"type": "integer"},
                        "break": {"type": "integer"}
                    }
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for the plan"
                },
                "items": {
                    "type": "array",
                    "description": "Ordered list of planned timeline items",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "start_time": {
                                "type": "string",
                                "description": "ISO 8601 timestamp (e.g. 2026-02-19T10:30:00+05:30)"
                            },
                            "end_time": {
                                "type": "string",
                                "description": "ISO 8601 timestamp"
                            },
                            "category": {
                                "type": "string",
                                "enum": ["work", "personal", "health", "break", "social", "family", "finance"]
                            },
                            "item_type": {
                                "type": "string",
                                "enum": ["focused_work", "meeting", "meal", "workout", "errand", "commute", "entertainment", "other"]
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "default": "medium"
                            },
                            "notes": {"type": "string"}
                        },
                        "required": ["title"]
                    }
                }
            },
            "required": ["plan_date"]
        }
    )


def _update_plan_item_tool() -> types.Tool:
    return types.Tool(
        name="update_plan_item",
        description=(
            "Update the status of a planned item. Called at check-in when items are completed, "
            "skipped, or linked to an actual journal event. Can also link to an actual_event_id "
            "to connect the planned item with what was logged in the journal."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "UUID of the planned item to update"
                },
                "status": {
                    "type": "string",
                    "enum": ["planned", "in-progress", "completed", "skipped", "modified", "replaced"],
                    "description": "New status for the item"
                },
                "actual_event_id": {
                    "type": "string",
                    "description": "UUID of the actual journal event linked to this item (optional)"
                },
                "status_notes": {
                    "type": "string",
                    "description": "Notes about the status change (e.g., reason for skipping)"
                }
            },
            "required": ["item_id", "status"]
        }
    )


def _get_plan_vs_actual_tool() -> types.Tool:
    return types.Tool(
        name="get_plan_vs_actual",
        description=(
            "Get a structured plan vs. actual comparison for a given date. "
            "Returns each planned item with its actual event (if linked), resolution status, "
            "and end-time delta in minutes. Includes summary stats: total, completed, skipped, "
            "pending, and completion rate. Uses the latest plan version if version is omitted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "plan_date": {
                    "type": "string",
                    "description": "Date to query (YYYY-MM-DD)"
                },
                "version": {
                    "type": "integer",
                    "description": "Plan version number (uses latest if omitted)"
                }
            },
            "required": ["plan_date"]
        }
    )


def _get_planning_insights_tool() -> types.Tool:
    return types.Tool(
        name="get_planning_insights",
        description=(
            "Get planning analytics over a date range. "
            "Returns overall completion rate, average items per day, category breakdown, "
            "day-of-week patterns, and generated insights. "
            "Useful for weekly reviews and understanding planning habits."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD, inclusive)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD, inclusive)"
                },
                "group_by": {
                    "type": "string",
                    "enum": ["week", "day_of_week", "category"],
                    "description": "Grouping dimension for breakdown",
                    "default": "week"
                }
            },
            "required": ["start_date", "end_date"]
        }
    )


def get_planning_tools() -> list[types.Tool]:
    return [
        _create_daily_plan_tool(),
        _update_plan_item_tool(),
        _get_plan_vs_actual_tool(),
        _get_planning_insights_tool(),
    ]
