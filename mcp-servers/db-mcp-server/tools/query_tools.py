"""
Structured Query MCP Tools

Tool definitions for the structured query language.
Exposed when QUERY_MODE=structured.
"""

from mcp import types

# All publicly queryable entities
_ENTITY_ENUM = [
    "events", "people", "locations", "exercises", "journal_entries",
    "workouts", "meals", "commutes", "entertainment", "reflections",
    "health_conditions", "health_condition_logs",
]


def structured_query() -> types.Tool:
    """
    Query tool — structured entity queries with filters, includes, and pagination.
    Replaces execute_sql_query for read operations.
    """
    return types.Tool(
        name="query",
        description=(
            "Query journal entities with structured filters. Returns domain objects with optional "
            "relationship hydration. Soft-delete filtering is automatic.\n\n"
            "ENTITIES: events, people, locations, exercises, journal_entries, "
            "workouts, meals, commutes, entertainment, reflections, health_conditions, health_condition_logs.\n\n"
            "FILTER OPERATORS: eq, neq, gt, gte, lt, lte, in, notIn, contains, startsWith, isNull.\n\n"
            "CROSS-ENTITY FILTERS: Use dot notation to filter by related entity fields. "
            "Example: {\"participants.name\": {\"contains\": \"Gauri\"}} filters events by participant name.\n\n"
            "DATE SHORTHAND: Use partial dates for range filtering. "
            "\"2026-01\" expands to the full month. \"2026\" expands to the full year.\n\n"
            "INCLUDES (relationship hydration):\n"
            "- events: participants, location, workout, meal, commute, entertainment\n"
            "- people: relationships\n"
            "- workouts: event, exercises (with nested sets)\n"
            "- meals: event, items\n"
            "- commutes: event, from_location, to_location\n"
            "- entertainment/reflections/health_conditions: event\n"
            "- health_condition_logs: condition"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "enum": _ENTITY_ENUM,
                    "description": "The entity type to query."
                },
                "where": {
                    "type": "object",
                    "description": (
                        "Filter conditions. Keys are field names (or dot-notation like 'participants.name'), "
                        "values are operator objects. "
                        "Example: {\"type\": {\"eq\": \"meal\"}, \"date\": {\"gte\": \"2026-01\"}}. "
                        "Shorthand: {\"type\": \"meal\"} equals {\"type\": {\"eq\": \"meal\"}}."
                    ),
                    "additionalProperties": True,
                },
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relationships to hydrate as nested objects.",
                },
                "orderBy": {
                    "type": "string",
                    "description": "Field name to order by. Defaults to entity's natural order.",
                },
                "orderDir": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort direction. Default: desc.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return. Default: 50, Max: 200.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of results to skip (for pagination). Default: 0.",
                },
            },
            "required": ["entity"],
        },
    )


def structured_aggregate() -> types.Tool:
    """
    Aggregate tool — counts, sums, averages with grouping.
    """
    return types.Tool(
        name="aggregate",
        description=(
            "Aggregate journal data with counts, sums, averages, min/max, and grouping. "
            "Uses the same filter syntax and entities as the query tool. "
            "Soft-delete filtering is automatic. "
            "Supports cross-entity filters and date shorthand."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "enum": _ENTITY_ENUM,
                    "description": "The entity type to aggregate."
                },
                "where": {
                    "type": "object",
                    "description": "Filter conditions (same syntax as query tool, including dot-notation and date shorthand).",
                    "additionalProperties": True,
                },
                "aggregate": {
                    "type": "object",
                    "description": (
                        "Aggregation functions to apply. "
                        "count: true for row count. sum/avg/min/max: field name to aggregate. "
                        "Example: {\"count\": true, \"avg\": \"duration\"}."
                    ),
                    "properties": {
                        "count": {"type": "boolean", "description": "Count matching rows."},
                        "sum": {"type": "string", "description": "Field to sum."},
                        "avg": {"type": "string", "description": "Field to average."},
                        "min": {"type": "string", "description": "Field to find minimum."},
                        "max": {"type": "string", "description": "Field to find maximum."},
                    },
                    "additionalProperties": False,
                },
                "groupBy": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fields to group by. Example: [\"type\"] to group events by type.",
                },
            },
            "required": ["entity"],
        },
    )
