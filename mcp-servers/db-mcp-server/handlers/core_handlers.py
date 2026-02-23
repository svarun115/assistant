"""
Core Database Operation Handlers
Handles: execute_sql_query, get_database_schema
"""

import json
import logging
from datetime import datetime
from typing import Any
from mcp import types

logger = logging.getLogger(__name__)


def serialize_result(obj):
    """Helper to serialize datetime and other non-JSON types"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def validate_query_security(query: str) -> tuple[bool, str]:
    """
    Validate that a SQL query is READ-ONLY and safe to execute.
    
    Returns: (is_safe: bool, error_message: str)
    
    ALLOWED:
    - SELECT: Data retrieval (with WHERE, ORDER BY, GROUP BY, aggregations, etc.)
    - WITH: CTEs for complex queries
    - EXPLAIN: Query planning analysis
    
    BLOCKED:
    - ALL WRITES: INSERT, UPDATE, DELETE (as top-level statement)
    - ALL DDL: CREATE, ALTER, DROP, TRUNCATE
    - ALL DCL: GRANT, REVOKE
    - DANGEROUS: VACUUM, ANALYZE, REINDEX (admin commands)
    
    Strategy: Only allow queries that are pure SELECT-based (SELECT, WITH...SELECT, EXPLAIN SELECT).
    Use strict word boundary checking on statement keywords only (not column names or values).
    """
    import re
    
    query_stripped = query.strip()
    query_upper = query_stripped.upper()
    
    # First check: query must start with allowed statement types
    allowed_starts = ('SELECT', 'WITH', 'EXPLAIN')
    if not query_upper.startswith(allowed_starts):
        return False, "❌ Query must start with SELECT, WITH, or EXPLAIN"
    
    # Second check: Look for write/dangerous operations that are statement keywords
    # We use word boundary (\b) to match only complete words, not parts of identifiers
    # These patterns must match complete SQL keywords, not column names containing these words
    
    dangerous_patterns = [
        # Write operations
        (r'\bINSERT\b', 'INSERT'),
        (r'\bUPDATE\b', 'UPDATE'),
        (r'\bDELETE\s+FROM\b', 'DELETE FROM'),  # DELETE keyword followed by FROM
        (r'\bTRUNCATE\b', 'TRUNCATE'),
        # DDL operations
        (r'\bCREATE\s+(TABLE|INDEX|VIEW|FUNCTION|PROCEDURE|SCHEMA|DATABASE)\b', 'CREATE'),
        (r'\bALTER\b', 'ALTER'),
        (r'\bDROP\b', 'DROP'),
        # DCL operations
        (r'\bGRANT\b', 'GRANT'),
        (r'\bREVOKE\b', 'REVOKE'),
        # Admin operations
        (r'\bVACUUM\b', 'VACUUM'),
        (r'\bANALYZE\b', 'ANALYZE'),
        (r'\bREINDEX\b', 'REINDEX'),
        # CALL would execute stored procedures that might write
        (r'\bCALL\b', 'CALL'),
    ]
    
    for pattern, keyword in dangerous_patterns:
        if re.search(pattern, query_upper):
            return False, f"❌ Query contains forbidden operation: {keyword}"
    
    return True, ""


def log_raw_query(query: str, params: list = None, query_type: str = "SELECT"):
    """Log raw SQL queries to identify patterns and missing tool coverage"""
    from pathlib import Path
    
    query_log_path = Path(__file__).parent.parent / "query_logs"
    query_log_path.mkdir(exist_ok=True)
    
    try:
        log_file = query_log_path / f"queries_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "query_type": query_type,
            "query": query.strip(),
            "params": params or [],
            "query_hash": hash(query.strip())
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    except Exception as e:
        logger.warning(f"Failed to log query: {e}")


async def handle_execute_sql_query(
    db, 
    pending_transactions: dict, 
    transaction_counter: int,
    arguments: dict[str, Any]
) -> tuple[list[types.TextContent], int]:
    """
    Execute SQL query - READ ONLY
    Returns (response, updated_transaction_counter)
    
    SECURITY MODEL:
    ✅ SELECT, WITH: Allowed for analysis queries
    ❌ ALL WRITES (INSERT, UPDATE, DELETE): Blocked
    ❌ DANGEROUS (DROP, ALTER, TRUNCATE, GRANT, REVOKE): Blocked
    
    This is a READ-ONLY interface. Use specialized tools for all writes:
    - create_event() for events
    - create_workout() for workouts
    - create_meal() for meals
    """
    query = arguments["query"]
    params = arguments.get("params", [])
    
    # ⚠️ SECURITY CHECK: Validate query is READ-ONLY
    is_safe, error_msg = validate_query_security(query)
    if not is_safe:
        log_raw_query(query, params, "BLOCKED")
        logger.warning(f"🚫 Blocked query: {query[:100]}... Reason: {error_msg}")
        
        return (
            [types.TextContent(
                type="text",
                text=json.dumps({"error": f"QUERY REJECTED\n\n{error_msg}\n\n💡 Use specialized tools for data writes:\n- create_event() for events\n- create_workout() for workouts\n- create_meal() for meals"}, indent=2)
            )],
            transaction_counter
        )
    
    # Log the query for analysis
    log_raw_query(query, params, "READ")
    logger.info(f"📊 Raw SQL query logged: READ - {query[:100]}...")
    
    # Execute the READ query
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            results = [dict(row) for row in rows]
            
            results_json = json.dumps(results, default=serialize_result, indent=2)
            
            return (
                [types.TextContent(
                    type="text",
                    text=f"Query returned {len(results)} rows:\n\n{results_json}"
                )],
                transaction_counter
            )
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return (
            [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Query error: {str(e)}"}, indent=2)
            )],
            transaction_counter
        )


async def handle_get_database_schema(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Get database schema information"""
    query = """
        SELECT 
            table_name,
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name NOT LIKE 'pg_%'
        ORDER BY table_name, ordinal_position
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
        
        # Group by table
        schema = {}
        for row in rows:
            table = row['table_name']
            if table not in schema:
                schema[table] = []
            schema[table].append({
                'column': row['column_name'],
                'type': row['data_type'],
                'nullable': row['is_nullable'] == 'YES',
                'default': row['column_default']
            })
        
        schema_json = json.dumps(schema, indent=2)
        
        return [types.TextContent(
            type="text",
            text=f"Database schema:\n\n{schema_json}"
        )]
