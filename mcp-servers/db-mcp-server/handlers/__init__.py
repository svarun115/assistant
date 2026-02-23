"""
Handler Registry - Maps tool names to handler functions

This module provides a centralized registry that routes tool calls to their
respective handler functions. Handlers are organized by category matching
the tools/ directory structure.

Architecture:
- Each handler module exports async functions: handle_<tool_name>(db, arguments)
- Special handlers (execute_sql_query, propose_write_query) return tuples with transaction_counter
- Instruction handlers don't require db connection
- Registry maps tool names to (module, needs_db, needs_repos, needs_transactions) tuples

Usage:
    from handlers import get_handler
    
    handler_info = get_handler(tool_name)
    if handler_info:
        handler, needs_db, needs_repos, needs_transactions = handler_info
        result = await handler(db, arguments)  # or handler(arguments) for instruction tools

NOTE: This registry includes ONLY write operations and core infrastructure.
All read operations (search_*, get_*, list_*) should use execute_sql_query instead.
See Issue #55 - SQL-first architecture redesign.
"""

from typing import Callable, Tuple, Optional


# Import all handler modules
from . import core_handlers
from . import entity_resolution_handlers
from . import workout_handlers
from . import meal_handlers
from . import event_handlers
from . import people_handlers
from . import travel_handlers
from . import entertainment_handlers
from . import health_handlers
from . import journal_handlers
from . import instruction_handlers
from . import planning_handlers
from . import entity_handlers



# Handler registry: {tool_name: (handler_function, needs_db, needs_repos, needs_transactions)}
# - needs_db: Handler requires database connection
# - needs_repos: Handler requires repository instances
# - needs_transactions: Handler modifies/accesses pending_transactions and transaction_counter
HANDLER_REGISTRY = {
    # Core database operations
    "execute_sql_query": (
        core_handlers.handle_execute_sql_query,
        True,  # needs_db
        False, # needs_repos
        True   # needs_transactions (returns updated counter)
    ),
    "get_database_schema": (
        core_handlers.handle_get_database_schema,
        True,
        False,
        False
    ),
    
    # Entity resolution - WRITE ONLY (read via execute_sql_query)
    "create_exercise": (
        entity_resolution_handlers.handle_create_exercise,
        True,  # needs_db
        False, # needs_repos (uses direct SQL)
        False
    ),
    "update_exercise": (
        entity_resolution_handlers.handle_update_exercise,
        True,  # needs_db
        False, # needs_repos (uses direct SQL)
        False
    ),
    "create_location": (
        entity_resolution_handlers.handle_create_location,
        False,
        True,  # needs_repos
        False
    ),
    "update_location": (
        entity_resolution_handlers.handle_update_location,
        False,
        True,  # needs_repos
        False
    ),
    
    # Workout tools - WRITE ONLY (read via execute_sql_query)
    "create_workout": (
        workout_handlers.handle_create_workout,
        True,  # needs_db
        True,  # needs_repos (uses get_or_create, validates exercises)
        False
    ),
    "update_workout": (
        workout_handlers.handle_update_workout,
        True,
        True,  # needs_repos
        False
    ),
    "reassign_exercise_in_workouts": (
        workout_handlers.handle_reassign_exercise_in_workouts,
        True,   # needs_db
        True,   # needs_repos (to validate exercises exist)
        False
    ),
    
    # Meal tools - WRITE ONLY (read via execute_sql_query)
    "create_meal": (
        meal_handlers.handle_create_meal,
        True,  # needs_db
        True,  # needs_repos (uses get_or_create)
        False
    ),
    "update_meal": (
        meal_handlers.handle_update_meal,
        True,  # needs_db
        True,  # needs_repos
        False
    ),
    
    # Event tools - WRITE ONLY (read via execute_sql_query)
    "create_event": (
        event_handlers.handle_create_event,
        True,  # needs_db (requires database connection)
        True,  # needs_repos (uses get_or_create)
        False
    ),
    "update_event": (
        event_handlers.handle_update_event,
        True,  # needs_db
        True,  # needs_repos
        False
    ),
    
    # Travel/commute tools - WRITE ONLY (read via execute_sql_query)
    "create_commute": (
        travel_handlers.handle_create_commute,
        True,  # needs_db
        True,  # needs_repos (uses get_or_create)
        False
    ),
    "update_commute": (
        travel_handlers.handle_update_commute,
        True,  # needs_db
        True,  # needs_repos (uses get_or_create)
        False
    ),
    
    
    # Note: Sleep, Reflection, and Work event tools have been consolidated
    # into the unified event_handlers above (create_event, update_event, delete_event, undelete_event)
    # with event_type parameter. Old tool names (create_sleep_event, create_reflection, create_work_block, etc.)
    # are DEPRECATED and have been removed. See EVENT_TYPE_CONSOLIDATION.md for details.
    
    # People management tools - WRITE ONLY (read via execute_sql_query)
    "create_person": (
        people_handlers.handle_create_person,
        False,
        True,  # needs_repos
        False
    ),
    "add_person_note": (
        people_handlers.handle_add_person_note,
        False,
        True,  # needs_repos
        False
    ),
    "add_person_relationship": (
        people_handlers.handle_add_person_relationship,
        False,
        True,  # needs_repos
        False
    ),
    "update_person": (
        people_handlers.handle_update_person,
        False,
        True,  # needs_repos
        False
    ),
    "update_person_relationship": (
        people_handlers.handle_update_person_relationship,
        False,
        True,  # needs_repos
        False
    ),
    "add_person_work": (
        people_handlers.handle_add_person_work,
        False,
        True,  # needs_repos
        False
    ),
    "add_person_education": (
        people_handlers.handle_add_person_education,
        False,
        True,  # needs_repos
        False
    ),
    "add_person_residence": (
        people_handlers.handle_add_person_residence,
        False,
        True,  # needs_repos
        False
    ),
    "update_person_work": (
        people_handlers.handle_update_person_work,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "update_person_education": (
        people_handlers.handle_update_person_education,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "update_person_residence": (
        people_handlers.handle_update_person_residence,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "update_person_note": (
        people_handlers.handle_update_person_note,
        True,   # needs_db
        False,  # doesn't need repos
        False
    ),
    "merge_duplicate_people": (
        people_handlers.handle_merge_duplicate_people,
        True,   # needs_db (direct SQL for bulk operations)
        True,   # needs_repos (to validate people exist)
        False
    ),

    # Health tracking tools - WRITE ONLY (read via execute_sql_query)
    "log_health_condition": (
        health_handlers.handle_log_health_condition,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "log_medicine": (
        health_handlers.handle_log_medicine,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "log_supplement": (
        health_handlers.handle_log_supplement,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "update_health_condition": (
        health_handlers.handle_update_health_condition,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "update_medicine": (
        health_handlers.handle_update_medicine,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "update_supplement": (
        health_handlers.handle_update_supplement,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "log_health_condition_update": (
        health_handlers.handle_log_health_condition_update,
        True,   # needs_db
        True,   # needs_repos (validate condition exists)
        False
    ),
    "update_health_condition_log": (
        health_handlers.handle_update_health_condition_log,
        True,   # needs_db
        False,  # doesn't need repos
        False
    ),

    # Entertainment tools - WRITE ONLY (read via execute_sql_query)
    "create_entertainment": (
        entertainment_handlers.handle_create_entertainment,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    
    # Journal/Memory tools
    "log_journal_entry": (
        journal_handlers.handle_log_journal_entry,
        False, # needs_db (handled by service/repo)
        True,  # needs_repos (to access memory service)
        False
    ),
    "search_journal_history": (
        journal_handlers.handle_search_journal_history,
        False,
        True,
        False
    ),
    # Alias for structured mode (same handler, renamed tool)
    "semantic_search": (
        journal_handlers.handle_search_journal_history,
        False,
        True,
        False
    ),
    "get_journal_by_date": (
        journal_handlers.handle_get_journal_by_date,
        False,
        True,
        False
    ),
    # Unified entity delete/restore (replaces 23 individual delete/undelete tools)
    "delete_entity": (
        entity_handlers.handle_delete_entity,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    "restore_entity": (
        entity_handlers.handle_restore_entity,
        True,   # needs_db
        True,   # needs_repos
        False
    ),
    
    # Instruction tools
    "get_journal_instructions": (
        instruction_handlers.handle_get_journal_instructions,
        False,
        False,
        False
    ),
    "get_domain_instructions": (
        instruction_handlers.handle_get_domain_instructions,
        False,
        False,
        False
    ),

    # Planning tools
    "create_daily_plan": (
        planning_handlers.handle_create_daily_plan,
        True,   # needs_db
        False,  # needs_repos
        False   # needs_transactions
    ),
    "update_plan_item": (
        planning_handlers.handle_update_plan_item,
        True,   # needs_db
        False,  # needs_repos
        False
    ),
    "get_plan_vs_actual": (
        planning_handlers.handle_get_plan_vs_actual,
        True,   # needs_db
        False,  # needs_repos
        False
    ),
    "get_planning_insights": (
        planning_handlers.handle_get_planning_insights,
        True,   # needs_db
        False,  # needs_repos
        False
    ),
}

# Conditionally register structured query handlers when QUERY_MODE=structured
try:
    from config import is_structured_query_mode
    if is_structured_query_mode():
        from . import query_handlers
        HANDLER_REGISTRY["query"] = (
            query_handlers.handle_query,
            True,   # needs_db
            False,  # needs_repos
            False,  # needs_transactions
        )
        HANDLER_REGISTRY["aggregate"] = (
            query_handlers.handle_aggregate,
            True,   # needs_db
            False,  # needs_repos
            False,  # needs_transactions
        )
except ImportError:
    pass  # Config not available (e.g., during isolated testing)


def get_handler(tool_name: str) -> Optional[Tuple[Callable, bool, bool, bool]]:
    """
    Get handler function and its requirements for a tool.

    Returns:
        Tuple of (handler_function, needs_db, needs_repos, needs_transactions) or None
    """
    return HANDLER_REGISTRY.get(tool_name)


def list_all_handlers() -> list[str]:
    """Get list of all registered tool names"""
    return list(HANDLER_REGISTRY.keys())


__all__ = [
    'get_handler',
    'list_all_handlers',
    'HANDLER_REGISTRY'
]
