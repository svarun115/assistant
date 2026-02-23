"""
MCP Tools Package
Modular organization with lazy discovery support.

Core tools (always loaded):
- Core database operations
- Entity resolution (search before create)
- Discovery tools (lazy loading triggers)
- Write operations (human-in-the-loop)

Specialized tools (loaded on-demand via discovery):
- Workout tools
- Meal tools
- Event tools
- Travel tools
- Entertainment tools
- Health tools
"""

from .core_tools import get_database_schema, execute_sql_query
from .workout_tools import get_workout_tools, get_exercise_tools
from .meal_tools import get_meal_tools
from .event_tools import get_event_tools
from .travel_tools import get_travel_tools
from .entertainment_tools import get_entertainment_tools
from .people_tools import get_people_tools
from .location_tools import get_location_tools
from .health_tools import get_health_tools
from .journal_tools import get_journal_tools
from .planning_tools import get_planning_tools
from .entity_tools import get_entity_tools
from .backup_tools import create_backup_sql, list_backups, inspect_backup, request_restore, create_backup_json
from .instruction_tools import get_journal_instructions, get_domain_instructions



def get_core_tool_catalog():
    """
    Get MCP tools. Read tool selection is gated by QUERY_MODE env var.

    QUERY_MODE=sql (default):
    - execute_sql_query: Direct SQL interface for SELECT queries (read-only)
    - get_database_schema: Schema reference and convenience views

    QUERY_MODE=structured:
    - query: Structured entity queries with filters, includes, pagination
    - aggregate: Counts, sums, averages with grouping

    WRITE OPERATIONS (always available, unchanged):
    - People, Locations, Events, Workouts, Exercises, Meals, Travel, Entertainment, Health, Journal
    """
    from config import is_structured_query_mode

    structured = is_structured_query_mode()
    tools = []

    # Read tools — gated by QUERY_MODE
    if structured:
        from .query_tools import structured_query, structured_aggregate
        tools.extend([structured_query(), structured_aggregate()])
    else:
        tools.extend([get_database_schema(), execute_sql_query()])

    # Write + domain tools
    tools.extend([
        *get_people_tools(),
        *get_location_tools(),
        *get_event_tools(),
        *get_workout_tools(),
        *get_exercise_tools(),
        *get_meal_tools(),
        *get_entertainment_tools(),
        *get_health_tools(),
        *get_travel_tools(),
        *get_journal_tools(structured_mode=structured),
        *get_planning_tools(),
        *get_entity_tools(),
        create_backup_sql(),
        create_backup_json(),
        list_backups(),
        inspect_backup(),
        request_restore(),
    ])

    # Instruction tools — only in SQL mode (structured mode uses skill files for context)
    if not structured:
        tools.extend([get_journal_instructions(), get_domain_instructions()])

    return tools



__all__ = [
    'get_core_tool_catalog',
    'get_database_schema',
    'execute_sql_query',
    'get_workout_tools',
    'get_exercise_tools',
    'get_meal_tools',
    'get_event_tools',
    'get_travel_tools',
    'get_entertainment_tools',
    'get_people_tools',
    'get_location_tools',
    'get_health_tools',
    'get_journal_tools',
    'get_planning_tools',
    'get_entity_tools',
    'create_backup_sql',
    'list_backups',
    'inspect_backup',
    'request_restore',
]

