"""
Query Builder

Translates structured query input into parameterized SQL.
All values are passed as asyncpg positional parameters ($1, $2, ...) — never interpolated.

Supports:
- Basic field filters (eq, neq, gt, gte, lt, lte, in, contains, isNull, etc.)
- Cross-entity dot-notation filters (e.g., "participants.name": {"contains": "Gauri"})
- Date range shorthand ("2026-01" expands to full month range)
- Automatic soft-delete injection
- Parameterized queries only (no string interpolation)
"""

import logging
import re
from datetime import date as date_type
from typing import Any, Optional

from .entities import ENTITIES, EntityConfig, FieldDef, RelationshipDef

logger = logging.getLogger(__name__)

# Operators that take a value parameter
VALUE_OPERATORS = {
    "eq": "=",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# Regex for partial date shorthand: YYYY or YYYY-MM
_PARTIAL_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?$")


def _expand_date_shorthand(value: str) -> tuple[Optional[date_type], Optional[date_type]]:
    """
    Expand a partial date string into a (start, end) date range.
    - "2026" → (date(2026,1,1), date(2027,1,1))
    - "2026-01" → (date(2026,1,1), date(2026,2,1))
    - "2026-01-15" → (None, None) — not a shorthand, use as-is
    Returns (start, end) or (None, None) if not a shorthand.
    """
    m = _PARTIAL_DATE_RE.match(value)
    if not m:
        return None, None

    year = int(m.group(1))
    month = m.group(2)

    if month:
        month_int = int(month)
        if month_int == 12:
            return date_type(year, month_int, 1), date_type(year + 1, 1, 1)
        else:
            return date_type(year, month_int, 1), date_type(year, month_int + 1, 1)
    else:
        return date_type(year, 1, 1), date_type(year + 1, 1, 1)


class QueryBuilder:
    """Builds parameterized SQL from structured query input."""

    def _resolve_column(self, entity_config: EntityConfig, field_name: str) -> tuple[str, FieldDef]:
        """
        Resolve a domain field name to its qualified column reference.
        Returns (qualified_column, field_def).
        """
        field_def = entity_config.fields[field_name]
        alias = entity_config.table_alias

        if field_def.is_expression:
            return field_def.column, field_def
        return f"{alias}.{field_def.column}", field_def

    def _resolve_cross_entity_filter(
        self,
        entity_config: EntityConfig,
        path: str,
        operators: dict,
        params: list,
        joins: dict[str, str],
    ) -> list[str]:
        """
        Resolve a dot-notation filter like "participants.name".

        Args:
            entity_config: The root entity config
            path: Dot-separated path like "participants.name"
            operators: Filter operators dict
            params: Parameter list to append to
            joins: Dict of alias → JOIN clause (mutated in place)

        Returns:
            List of SQL condition strings.
        """
        parts = path.split(".", 1)
        if len(parts) != 2:
            return []

        rel_name, field_name = parts
        rel = entity_config.relationships.get(rel_name)
        if not rel:
            return []

        target_config = ENTITIES.get(rel.target_entity)
        if not target_config or field_name not in target_config.fields:
            return []

        # Generate a unique alias for this join
        join_alias = f"_j_{rel_name}"
        target_col_ref = f"{join_alias}.{target_config.fields[field_name].column}"
        target_field_def = target_config.fields[field_name]

        # Build JOIN if not already added
        if join_alias not in joins:
            root_alias = entity_config.table_alias

            if rel.type == "many_through":
                # Need two joins: root → junction → target
                jt_alias = f"_jt_{rel_name}"
                joins[jt_alias] = (
                    f"JOIN {rel.through_table} {jt_alias} "
                    f"ON {jt_alias}.{rel.through_local} = {root_alias}.{rel.local_key}"
                )
                joins[join_alias] = (
                    f"JOIN {target_config.table} {join_alias} "
                    f"ON {join_alias}.{rel.target_key} = {jt_alias}.{rel.through_target}"
                )
            elif rel.type == "belongs_to":
                joins[join_alias] = (
                    f"JOIN {target_config.table} {join_alias} "
                    f"ON {join_alias}.{rel.target_key} = {root_alias}.{rel.local_key}"
                )
            elif rel.type in ("has_one", "has_many"):
                joins[join_alias] = (
                    f"JOIN {target_config.table} {join_alias} "
                    f"ON {join_alias}.{rel.target_key} = {root_alias}.{rel.local_key}"
                )

            # Add soft-delete filter for the joined target
            if target_config.soft_delete:
                sd_col = f"{join_alias}.{target_config.soft_delete.flag_column}"
                joins[f"_sd_{join_alias}"] = None  # sentinel
                # We'll add the condition inline

        # Build filter conditions on the joined column
        conditions = []
        if not isinstance(operators, dict):
            operators = {"eq": operators}

        for op, value in operators.items():
            conditions.extend(
                self._build_single_filter(target_col_ref, target_field_def, op, value, params)
            )

        # Add soft-delete condition for the target if applicable
        if target_config.soft_delete:
            sd_key = f"_sd_{join_alias}"
            if sd_key in joins and joins[sd_key] is None:
                conditions.append(f"{join_alias}.{target_config.soft_delete.flag_column} = FALSE")
                joins[sd_key] = "applied"  # Mark as applied

        return conditions

    def _build_single_filter(
        self, col: str, field_def: FieldDef, op: str, value: Any, params: list
    ) -> list[str]:
        """Build a single filter condition for a column + operator + value."""
        conditions = []

        if op in VALUE_OPERATORS:
            # Check for date shorthand on date/timestamp fields
            if field_def.type in ("date", "timestamp") and isinstance(value, str):
                start, end = _expand_date_shorthand(value)
                if start is not None:
                    # Expand shorthand: eq → between, gte → >=start, lte → <end
                    if op == "eq":
                        params.append(start)
                        conditions.append(f"{col} >= ${len(params)}")
                        params.append(end)
                        conditions.append(f"{col} < ${len(params)}")
                        return conditions
                    elif op in ("gte", "gt"):
                        params.append(start)
                        conditions.append(f"{col} >= ${len(params)}")
                        return conditions
                    elif op in ("lte", "lt"):
                        params.append(end)
                        conditions.append(f"{col} < ${len(params)}")
                        return conditions
                # Not a shorthand — convert full date string to date object for asyncpg
                if field_def.type == "date":
                    value = date_type.fromisoformat(value)

            params.append(value)
            conditions.append(f"{col} {VALUE_OPERATORS[op]} ${len(params)}")

        elif op == "in":
            # Convert date strings to date objects for date fields
            if field_def.type == "date" and isinstance(value, list):
                value = [date_type.fromisoformat(v) if isinstance(v, str) else v for v in value]
            params.append(value)
            conditions.append(f"{col} = ANY(${len(params)})")

        elif op == "notIn":
            # Convert date strings to date objects for date fields
            if field_def.type == "date" and isinstance(value, list):
                value = [date_type.fromisoformat(v) if isinstance(v, str) else v for v in value]
            params.append(value)
            conditions.append(f"{col} != ALL(${len(params)})")

        elif op == "contains":
            if field_def.type == "array":
                params.append([value])
                conditions.append(f"{col} @> ${len(params)}")
            else:
                params.append(f"%{value}%")
                conditions.append(f"{col} ILIKE ${len(params)}")

        elif op == "startsWith":
            params.append(f"{value}%")
            conditions.append(f"{col} ILIKE ${len(params)}")

        elif op == "isNull":
            if value:
                conditions.append(f"{col} IS NULL")
            else:
                conditions.append(f"{col} IS NOT NULL")

        elif op == "overlaps":
            params.append(value)
            conditions.append(f"{col} && ${len(params)}")

        return conditions

    def _build_filter(
        self,
        entity_config: EntityConfig,
        where: dict[str, Any],
        params: list,
        joins: Optional[dict[str, str]] = None,
    ) -> list[str]:
        """
        Build WHERE clause fragments from filter dict.
        Handles both direct fields and dot-notation cross-entity filters.
        """
        conditions = []

        for field_name, operators in where.items():
            # Cross-entity filter (dot notation)
            if "." in field_name:
                if joins is not None:
                    conditions.extend(
                        self._resolve_cross_entity_filter(entity_config, field_name, operators, params, joins)
                    )
                continue

            # Direct field filter
            if field_name not in entity_config.fields:
                continue

            col, field_def = self._resolve_column(entity_config, field_name)

            if not isinstance(operators, dict):
                operators = {"eq": operators}

            for op, value in operators.items():
                conditions.extend(self._build_single_filter(col, field_def, op, value, params))

        return conditions

    def _build_soft_delete_filter(self, entity_config: EntityConfig) -> str:
        """Build the soft-delete WHERE clause."""
        if entity_config.soft_delete:
            alias = entity_config.table_alias
            return f"{alias}.{entity_config.soft_delete.flag_column} = FALSE"
        return ""

    def _build_order(self, entity_config: EntityConfig, order_by: Optional[str], order_dir: str) -> str:
        """Build ORDER BY clause."""
        if order_by and order_by in entity_config.fields:
            col, _ = self._resolve_column(entity_config, order_by)
            direction = "DESC" if order_dir.lower() == "desc" else "ASC"
            return f"ORDER BY {col} {direction}"
        return f"ORDER BY {entity_config.default_order}"

    def _build_join_clause(self, joins: dict[str, str]) -> str:
        """Build JOIN clauses from the joins dict."""
        join_parts = []
        for alias, join_sql in joins.items():
            if join_sql and join_sql != "applied":
                join_parts.append(join_sql)
        return " ".join(join_parts)

    def build_select(
        self,
        entity: str,
        where: Optional[dict] = None,
        order_by: Optional[str] = None,
        order_dir: str = "desc",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> tuple[str, list]:
        """
        Build a SELECT query for an entity.
        Returns (sql, params).
        """
        entity_config = ENTITIES[entity]
        alias = entity_config.table_alias
        params: list = []
        joins: dict[str, str] = {}

        # SELECT columns — use domain field names as aliases
        select_parts = []
        for field_name, field_def in entity_config.fields.items():
            if field_def.is_expression:
                select_parts.append(f"{field_def.column} AS {field_name}")
            else:
                select_parts.append(f"{alias}.{field_def.column} AS {field_name}")

        select_clause = ", ".join(select_parts)

        # WHERE conditions
        conditions = []
        soft_delete = self._build_soft_delete_filter(entity_config)
        if soft_delete:
            conditions.append(soft_delete)

        if where:
            conditions.extend(self._build_filter(entity_config, where, params, joins))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # JOINs (from cross-entity filters)
        join_clause = self._build_join_clause(joins)

        # ORDER BY
        order_clause = self._build_order(entity_config, order_by, order_dir)

        # LIMIT / OFFSET
        effective_limit = min(limit, MAX_LIMIT)
        params.append(effective_limit)
        limit_clause = f"LIMIT ${len(params)}"
        params.append(offset)
        offset_clause = f"OFFSET ${len(params)}"

        # Use DISTINCT when cross-entity joins are present (to avoid duplicate rows from many-through)
        distinct = "DISTINCT " if joins else ""

        sql = f"SELECT {distinct}{select_clause} FROM {entity_config.table} {alias} {join_clause} {where_clause} {order_clause} {limit_clause} {offset_clause}"

        return " ".join(sql.split()), params  # Normalize whitespace

    def build_count(
        self,
        entity: str,
        where: Optional[dict] = None,
    ) -> tuple[str, list]:
        """
        Build a COUNT query for an entity (same filters, no pagination).
        Returns (sql, params).
        """
        entity_config = ENTITIES[entity]
        alias = entity_config.table_alias
        params: list = []
        joins: dict[str, str] = {}

        conditions = []
        soft_delete = self._build_soft_delete_filter(entity_config)
        if soft_delete:
            conditions.append(soft_delete)

        if where:
            conditions.extend(self._build_filter(entity_config, where, params, joins))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        join_clause = self._build_join_clause(joins)

        # Use COUNT(DISTINCT id) when joins present
        count_expr = f"COUNT(DISTINCT {alias}.id)" if joins else "COUNT(*)"

        sql = f"SELECT {count_expr} AS total FROM {entity_config.table} {alias} {join_clause} {where_clause}"

        return " ".join(sql.split()), params

    def build_aggregate(
        self,
        entity: str,
        where: Optional[dict] = None,
        aggregate: Optional[dict] = None,
        group_by: Optional[list[str]] = None,
    ) -> tuple[str, list]:
        """
        Build an aggregate query.
        Returns (sql, params).
        """
        entity_config = ENTITIES[entity]
        alias = entity_config.table_alias
        params: list = []
        joins: dict[str, str] = {}

        # Build SELECT with aggregation functions
        select_parts = []

        if aggregate:
            if aggregate.get("count"):
                select_parts.append("COUNT(*) AS count")
            for func in ("sum", "avg", "min", "max"):
                field_name = aggregate.get(func)
                if field_name and field_name in entity_config.fields:
                    col, _ = self._resolve_column(entity_config, field_name)
                    select_parts.append(f"{func.upper()}({col}) AS {func}")

        if not select_parts:
            select_parts.append("COUNT(*) AS count")

        # Group by fields
        group_cols = []
        if group_by:
            for field_name in group_by:
                if field_name in entity_config.fields:
                    col, _ = self._resolve_column(entity_config, field_name)
                    group_cols.append(col)
                    field_def = entity_config.fields[field_name]
                    if field_def.is_expression:
                        select_parts.insert(0, f"{field_def.column} AS {field_name}")
                    else:
                        select_parts.insert(0, f"{col} AS {field_name}")

        select_clause = ", ".join(select_parts)

        # WHERE
        conditions = []
        soft_delete = self._build_soft_delete_filter(entity_config)
        if soft_delete:
            conditions.append(soft_delete)

        if where:
            conditions.extend(self._build_filter(entity_config, where, params, joins))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        join_clause = self._build_join_clause(joins)

        # GROUP BY
        group_clause = f"GROUP BY {', '.join(group_cols)}" if group_cols else ""

        # ORDER BY group columns for consistent output
        order_clause = f"ORDER BY {', '.join(group_cols)}" if group_cols else ""

        sql = f"SELECT {select_clause} FROM {entity_config.table} {alias} {join_clause} {where_clause} {group_clause} {order_clause}"

        return " ".join(sql.split()), params
