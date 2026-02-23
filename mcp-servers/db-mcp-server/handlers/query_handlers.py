"""
Structured Query Handlers

Handles the `query` and `aggregate` MCP tools.
Validates input, builds SQL, executes, hydrates relationships, returns domain objects.
"""

import json
import logging
from datetime import datetime, date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from mcp import types

from query.builder import QueryBuilder
from query.hydrator import Hydrator
from query.validators import validate_query_input, validate_aggregate_input

logger = logging.getLogger(__name__)

builder = QueryBuilder()
hydrator = Hydrator()


def _serialize(obj: Any) -> Any:
    """JSON serialization helper for non-native types."""
    if obj is None or isinstance(obj, (bool, int, float, str, list)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


async def handle_query(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Handle the `query` tool — structured entity queries.

    Flow:
    1. Validate input
    2. Build SELECT + COUNT SQL
    3. Execute both queries
    4. Hydrate includes
    5. Return structured response
    """
    # Parse where clause if it's a JSON string (MCP sometimes sends objects as strings)
    where = arguments.get("where")
    if isinstance(where, str):
        try:
            where = json.loads(where)
            arguments["where"] = where
        except json.JSONDecodeError:
            error_response = {"error": True, "code": "INVALID_JSON", "message": "where parameter must be a valid JSON object"}
            return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]

    # Parse include array if it's a JSON string
    includes = arguments.get("include")
    if isinstance(includes, str):
        try:
            includes = json.loads(includes)
            arguments["include"] = includes
        except json.JSONDecodeError:
            error_response = {"error": True, "code": "INVALID_JSON", "message": "include parameter must be a valid JSON array"}
            return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]

    # 1. Validate
    validation_error = validate_query_input(arguments)
    if validation_error:
        return [types.TextContent(type="text", text=json.dumps(validation_error, indent=2))]

    entity = arguments["entity"]
    where = arguments.get("where")
    includes = arguments.get("include", [])
    order_by = arguments.get("orderBy")
    order_dir = arguments.get("orderDir", "desc")
    limit = arguments.get("limit", 50)
    offset = arguments.get("offset", 0)

    try:
        # 2. Build SQL
        select_sql, select_params = builder.build_select(
            entity=entity, where=where, order_by=order_by,
            order_dir=order_dir, limit=limit, offset=offset,
        )
        count_sql, count_params = builder.build_count(entity=entity, where=where)

        logger.info(f"query tool: {entity} — SQL: {select_sql[:120]}...")

        # 3. Execute
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(select_sql, *select_params)
            count_row = await conn.fetchrow(count_sql, *count_params)

        total = count_row["total"] if count_row else 0
        results = [{k: _serialize(v) for k, v in dict(r).items()} for r in rows]

        # 4. Hydrate includes
        if includes and results:
            results = await hydrator.hydrate(db, entity, results, includes)

        # 5. Build response
        effective_limit = min(limit, 200)
        response = {
            "entity": entity,
            "count": len(results),
            "total": total,
            "limit": effective_limit,
            "offset": offset,
            "hasMore": (offset + len(results)) < total,
            "results": results,
        }

        return [types.TextContent(type="text", text=json.dumps(response, indent=2, default=_serialize))]

    except Exception as e:
        logger.error(f"Query execution error: {e}", exc_info=True)
        error_response = {"error": True, "code": "QUERY_ERROR", "message": str(e)}
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]


async def handle_aggregate(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Handle the `aggregate` tool — counts, sums, averages with grouping.

    Flow:
    1. Validate input
    2. Build aggregate SQL
    3. Execute
    4. Return structured response
    """
    # Parse where clause if it's a JSON string (MCP sometimes sends objects as strings)
    where = arguments.get("where")
    if isinstance(where, str):
        try:
            where = json.loads(where)
            arguments["where"] = where
        except json.JSONDecodeError:
            error_response = {"error": True, "code": "INVALID_JSON", "message": "where parameter must be a valid JSON object"}
            return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]

    # Parse aggregate object if it's a JSON string
    aggregate = arguments.get("aggregate")
    if isinstance(aggregate, str):
        try:
            aggregate = json.loads(aggregate)
            arguments["aggregate"] = aggregate
        except json.JSONDecodeError:
            error_response = {"error": True, "code": "INVALID_JSON", "message": "aggregate parameter must be a valid JSON object"}
            return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]

    # Parse groupBy array if it's a JSON string
    group_by = arguments.get("groupBy")
    if isinstance(group_by, str):
        try:
            group_by = json.loads(group_by)
            arguments["groupBy"] = group_by
        except json.JSONDecodeError:
            error_response = {"error": True, "code": "INVALID_JSON", "message": "groupBy parameter must be a valid JSON array"}
            return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]

    # 1. Validate
    validation_error = validate_aggregate_input(arguments)
    if validation_error:
        return [types.TextContent(type="text", text=json.dumps(validation_error, indent=2))]

    entity = arguments["entity"]
    where = arguments.get("where")
    aggregate = arguments.get("aggregate", {"count": True})
    group_by = arguments.get("groupBy", [])

    try:
        # 2. Build SQL
        sql, params = builder.build_aggregate(
            entity=entity, where=where, aggregate=aggregate, group_by=group_by,
        )

        logger.info(f"aggregate tool: {entity} — SQL: {sql[:120]}...")

        # 3. Execute
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        results = [{k: _serialize(v) for k, v in dict(r).items()} for r in rows]

        # 4. Build response
        response = {
            "entity": entity,
            "aggregation": True,
            "results": results,
        }

        return [types.TextContent(type="text", text=json.dumps(response, indent=2, default=_serialize))]

    except Exception as e:
        logger.error(f"Aggregate execution error: {e}", exc_info=True)
        error_response = {"error": True, "code": "QUERY_ERROR", "message": str(e)}
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]
