"""
Relationship Hydrator

Batch-loads related entities and nests them into parent rows.
Uses batch queries (one per include) to avoid N+1 problems.
"""

import logging
from collections import defaultdict
from datetime import datetime, date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from .entities import ENTITIES, EntityConfig, RelationshipDef

logger = logging.getLogger(__name__)


def _serialize(obj: Any) -> Any:
    """Serialize non-JSON-native types."""
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


def _row_to_dict(row) -> dict:
    """Convert an asyncpg Record to a serializable dict."""
    return {k: _serialize(v) for k, v in dict(row).items()}


class Hydrator:
    """Batch-loads and attaches related entities to parent result rows."""

    async def hydrate(
        self,
        db,
        entity_name: str,
        rows: list[dict],
        includes: list[str],
    ) -> list[dict]:
        """
        For each include, batch-fetch related rows and nest them into parents.

        Args:
            db: DatabaseConnection instance
            entity_name: Name of the parent entity
            rows: List of parent entity dicts (already serialized)
            includes: List of relationship names to hydrate

        Returns:
            The same rows list, with included relationships added as nested dicts/lists.
        """
        if not rows or not includes:
            return rows

        entity_config = ENTITIES.get(entity_name)
        if not entity_config:
            return rows

        for include_name in includes:
            rel = entity_config.relationships.get(include_name)
            if not rel:
                logger.warning(f"Unknown include '{include_name}' on entity '{entity_name}'")
                continue

            if rel.type == "belongs_to":
                await self._hydrate_belongs_to(db, rows, include_name, rel)
            elif rel.type == "has_one":
                await self._hydrate_has_one(db, rows, include_name, rel)
            elif rel.type == "many_through":
                await self._hydrate_many_through(db, rows, include_name, rel)
            elif rel.type == "has_many":
                await self._hydrate_has_many(db, rows, include_name, rel)

        return rows

    async def _hydrate_belongs_to(
        self, db, rows: list[dict], include_name: str, rel: RelationshipDef
    ):
        """
        Hydrate a belongs_to relationship (e.g., events→location).
        Collects unique FK values, batch-fetches targets, attaches.
        """
        target_config = ENTITIES.get(rel.target_entity)
        if not target_config:
            return

        # Collect unique FK values
        fk_values = list({
            row.get(rel.local_key) for row in rows
            if row.get(rel.local_key) is not None
        })

        if not fk_values:
            for row in rows:
                row[include_name] = None
            return

        # Batch fetch
        target_alias = target_config.table_alias
        soft_delete = ""
        if target_config.soft_delete:
            soft_delete = f"AND {target_alias}.{target_config.soft_delete.flag_column} = FALSE"

        sql = f"SELECT * FROM {target_config.table} {target_alias} WHERE {target_alias}.{rel.target_key} = ANY($1) {soft_delete}"
        async with db.pool.acquire() as conn:
            target_rows = await conn.fetch(sql, fk_values)

        # Index by PK
        target_map = {str(_serialize(r[rel.target_key])): _row_to_dict(r) for r in target_rows}

        # Attach
        for row in rows:
            fk = row.get(rel.local_key)
            row[include_name] = target_map.get(str(fk)) if fk else None

    async def _hydrate_has_one(
        self, db, rows: list[dict], include_name: str, rel: RelationshipDef
    ):
        """
        Hydrate a has_one relationship (e.g., events→workout).
        The target has an FK pointing back to the parent.
        """
        target_config = ENTITIES.get(rel.target_entity)
        if not target_config:
            return

        # Collect parent IDs
        parent_ids = [row.get(rel.local_key) for row in rows if row.get(rel.local_key)]
        if not parent_ids:
            for row in rows:
                row[include_name] = None
            return

        target_alias = target_config.table_alias
        soft_delete = ""
        if target_config.soft_delete:
            soft_delete = f"AND {target_alias}.{target_config.soft_delete.flag_column} = FALSE"

        sql = f"SELECT * FROM {target_config.table} {target_alias} WHERE {target_alias}.{rel.target_key} = ANY($1) {soft_delete}"
        async with db.pool.acquire() as conn:
            target_rows = await conn.fetch(sql, parent_ids)

        # Index by the FK that points back to parent
        target_map = {str(_serialize(r[rel.target_key])): _row_to_dict(r) for r in target_rows}

        for row in rows:
            pk = str(row.get(rel.local_key, ""))
            row[include_name] = target_map.get(pk)

    async def _hydrate_many_through(
        self, db, rows: list[dict], include_name: str, rel: RelationshipDef
    ):
        """
        Hydrate a many-through-junction relationship (e.g., events→participants via event_participants).
        """
        target_config = ENTITIES.get(rel.target_entity)
        if not target_config:
            return

        parent_ids = [row.get(rel.local_key) for row in rows if row.get(rel.local_key)]
        if not parent_ids:
            for row in rows:
                row[include_name] = []
            return

        # Build join query: junction + target
        target_alias = target_config.table_alias
        jt = "jt"  # junction table alias

        # Select target columns + junction extra fields + the junction FK for grouping
        select_parts = [f"{jt}.{rel.through_local} AS _parent_id"]
        select_parts.append(f"{target_alias}.*")
        for ef in rel.extra_fields:
            select_parts.append(f"{jt}.{ef}")

        select_clause = ", ".join(select_parts)

        soft_delete = ""
        if target_config.soft_delete:
            soft_delete = f"AND {target_alias}.{target_config.soft_delete.flag_column} = FALSE"

        sql = (
            f"SELECT {select_clause} "
            f"FROM {rel.through_table} {jt} "
            f"JOIN {target_config.table} {target_alias} ON {target_alias}.{rel.target_key} = {jt}.{rel.through_target} "
            f"WHERE {jt}.{rel.through_local} = ANY($1) {soft_delete}"
        )

        async with db.pool.acquire() as conn:
            junction_rows = await conn.fetch(sql, parent_ids)

        # Group by parent ID
        grouped: dict[str, list[dict]] = defaultdict(list)
        for r in junction_rows:
            row_dict = _row_to_dict(r)
            parent_id = str(row_dict.pop("_parent_id", ""))
            grouped[parent_id].append(row_dict)

        for row in rows:
            pk = str(row.get(rel.local_key, ""))
            row[include_name] = grouped.get(pk, [])

    async def _hydrate_has_many(
        self, db, rows: list[dict], include_name: str, rel: RelationshipDef
    ):
        """
        Hydrate a has_many relationship (direct FK, no junction table).
        For internal entities (prefixed with _), automatically hydrates their
        own relationships too (e.g., _workout_exercises → exercise + sets).
        """
        target_config = ENTITIES.get(rel.target_entity)
        if not target_config:
            return

        parent_ids = [row.get(rel.local_key) for row in rows if row.get(rel.local_key)]
        if not parent_ids:
            for row in rows:
                row[include_name] = []
            return

        target_alias = target_config.table_alias
        soft_delete = ""
        if target_config.soft_delete:
            soft_delete = f"AND {target_alias}.{target_config.soft_delete.flag_column} = FALSE"

        sql = f"SELECT * FROM {target_config.table} {target_alias} WHERE {target_alias}.{rel.target_key} = ANY($1) {soft_delete}"
        async with db.pool.acquire() as conn:
            target_rows = await conn.fetch(sql, parent_ids)

        child_rows = [_row_to_dict(r) for r in target_rows]

        # Auto-hydrate nested relationships for internal entities (e.g., _workout_exercises → exercise, sets)
        if rel.target_entity.startswith("_") and target_config.relationships and child_rows:
            nested_includes = list(target_config.relationships.keys())
            await self.hydrate(db, rel.target_entity, child_rows, nested_includes)

        grouped: dict[str, list[dict]] = defaultdict(list)
        for row_dict in child_rows:
            parent_id = str(row_dict.get(rel.target_key, ""))
            grouped[parent_id].append(row_dict)

        for row in rows:
            pk = str(row.get(rel.local_key, ""))
            row[include_name] = grouped.get(pk, [])
