from typing import List
from mcp import types


def get_journal_tools(structured_mode: bool = False) -> List[types.Tool]:
    """
    Get tools for Journal/Memory system.

    Args:
        structured_mode: If True, excludes tools redundant with query/aggregate
                        (get_journal_by_date) and renames semantic search for clarity.
    """
    tools = [
        types.Tool(
            name="log_journal_entry",
            description="Log a raw journal entry (thought, reflection, fact) to memory. Saves to database and indexes for semantic search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The raw content of the entry"
                    },
                    "entry_type": {
                        "type": "string",
                        "description": "Type of entry (journal, reflection, log, fact, idea)",
                        "default": "journal"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tags for categorization"
                    },
                    "entry_date": {
                        "type": "string",
                        "description": "Date of entry (YYYY-MM-DD). Defaults to today."
                    }
                },
                "required": ["text"]
            }
        ),

        # Semantic search — renamed in structured mode for clarity
        types.Tool(
            name="semantic_search" if structured_mode else "search_journal_history",
            description="Semantically search your journal history using natural language. Supports optional filtering by date range, entry types, and tags.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'how have I been sleeping?', 'thoughts on career', 'workout progress')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results to return (default 5)",
                        "default": 5
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional: Only return entries from this date onward (YYYY-MM-DD)."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional: Only return entries up to this date (YYYY-MM-DD)."
                    },
                    "entry_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["journal", "reflection", "log", "fact", "idea"]
                        },
                        "description": "Optional: Filter by specific entry types."
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Filter by tags. Returns entries with at least one of these tags."
                    }
                },
                "required": ["query"]
            }
        ),

    ]
    # Delete/restore: use delete_entity / restore_entity with entity_type="journal_entry"

    # get_journal_by_date is redundant in structured mode (use query tool instead)
    if not structured_mode:
        tools.append(types.Tool(
            name="get_journal_by_date",
            description="Get all raw journal entries for a specific date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entry_date": {
                        "type": "string",
                        "description": "Date to retrieve (YYYY-MM-DD)"
                    }
                },
                "required": ["entry_date"]
            }
        ))

    return tools
