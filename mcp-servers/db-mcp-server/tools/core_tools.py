"""
Core MCP Tools
Essential tools for database operations and schema exploration.
"""

from mcp import types


def get_database_schema() -> types.Tool:
    """
    Returns the database schema tool for exploring the journal database structure.
    """
    return types.Tool(
        name="get_database_schema",
        description="Get the database schema information including all tables, columns, data types, and relationships. Use this to understand the database structure before writing SQL queries.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )


def execute_sql_query() -> types.Tool:
    """
    Returns the SQL query execution tool for flexible read operations.
    Part of SQL-first architecture (Issue #55).
    """
    return types.Tool(
        name="execute_sql_query",
        description="Execute SELECT queries against the journal database. Use this for all read operations - searching, filtering, joins, aggregations. Write-only SQL (INSERT/UPDATE/DELETE) is handled by specialized tools for safety. Returns query results as rows with column names. Supports all PostgreSQL SELECT syntax including JOINs, CTEs, window functions, and convenience views.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SELECT query to execute. Must be a read-only query (SELECT only, no INSERT/UPDATE/DELETE). Use this for: searching records, filtering by date/criteria, complex joins, aggregations, validation queries, etc."
                }
            },
            "required": ["query"]
        }
    )
