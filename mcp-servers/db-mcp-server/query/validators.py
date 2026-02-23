"""
Input Validators

Validates structured query input and returns helpful error messages
with valid field/entity/operator suggestions.
"""

from typing import Any, Optional

from .entities import ENTITIES, get_entity_names

VALID_OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "notIn", "contains", "startsWith", "overlaps", "isNull"}
VALID_AGGREGATE_FUNCS = {"count", "sum", "avg", "min", "max"}


def _validate_dot_notation(entity: str, entity_config, field_path: str, errors: list):
    """Validate a dot-notation cross-entity filter path."""
    parts = field_path.split(".", 1)
    if len(parts) != 2:
        errors.append(_error("INVALID_FIELD", f"where.{field_path}", f"Invalid dot-notation path '{field_path}'"))
        return

    rel_name, target_field = parts

    if rel_name not in entity_config.relationships:
        errors.append(_error(
            "INVALID_RELATIONSHIP", f"where.{field_path}",
            f"Unknown relationship '{rel_name}' on entity '{entity}'",
            validRelationships=list(entity_config.relationships.keys()),
        ))
        return

    target_entity_name = entity_config.relationships[rel_name].target_entity
    target_config = ENTITIES.get(target_entity_name)
    if not target_config:
        errors.append(_error("INVALID_RELATIONSHIP", f"where.{field_path}", f"Target entity '{target_entity_name}' not configured"))
        return

    if target_field not in target_config.fields:
        errors.append(_error(
            "UNKNOWN_FIELD", f"where.{field_path}",
            f"Unknown field '{target_field}' on entity '{target_entity_name}'",
            validFields=list(target_config.fields.keys()),
        ))


def _error(code: str, path: str, message: str, **extra) -> dict:
    """Build a structured validation error."""
    err = {"code": code, "path": path, "message": message}
    err.update(extra)
    return err


def validate_query_input(arguments: dict[str, Any]) -> Optional[dict]:
    """
    Validate input for the query tool.
    Returns error dict if invalid, None if valid.
    """
    errors = []

    # Entity validation
    entity = arguments.get("entity")
    if not entity:
        errors.append(_error("MISSING_ENTITY", "entity", "Entity is required", validEntities=get_entity_names()))
    elif entity not in ENTITIES:
        errors.append(_error("UNKNOWN_ENTITY", "entity", f"Unknown entity '{entity}'", validEntities=get_entity_names()))

    if errors:
        return {"error": True, "code": "VALIDATION_ERROR", "errors": errors}

    entity_config = ENTITIES[entity]

    # Where validation
    where = arguments.get("where", {})
    if where:
        for field_name, operators in where.items():
            # Cross-entity dot notation (e.g., "participants.name")
            if "." in field_name:
                _validate_dot_notation(entity, entity_config, field_name, errors)
            elif field_name not in entity_config.fields:
                # Suggest dot notation if field looks like it could be a relationship path
                hint = ""
                if field_name in entity_config.relationships:
                    target_entity = entity_config.relationships[field_name].target_entity
                    target_config = ENTITIES.get(target_entity)
                    if target_config:
                        hint = f" Did you mean '{field_name}.<field>'? Valid fields on {target_entity}: {list(target_config.fields.keys())}"
                errors.append(_error(
                    "UNKNOWN_FIELD", f"where.{field_name}",
                    f"Unknown field '{field_name}' on entity '{entity}'.{hint}",
                    validFields=list(entity_config.fields.keys()),
                ))
                continue

            if isinstance(operators, dict):
                for op in operators:
                    if op not in VALID_OPERATORS:
                        errors.append(_error(
                            "INVALID_OPERATOR", f"where.{field_name}.{op}",
                            f"Invalid operator '{op}'",
                            validOperators=list(VALID_OPERATORS),
                        ))

    # Include validation
    includes = arguments.get("include", [])
    if includes:
        for inc in includes:
            if inc not in entity_config.relationships:
                errors.append(_error(
                    "INVALID_RELATIONSHIP", f"include.{inc}",
                    f"Unknown relationship '{inc}' on entity '{entity}'",
                    validRelationships=list(entity_config.relationships.keys()),
                ))

    # OrderBy validation
    order_by = arguments.get("orderBy")
    if order_by and order_by not in entity_config.fields:
        errors.append(_error(
            "UNKNOWN_FIELD", "orderBy",
            f"Cannot order by unknown field '{order_by}'",
            validFields=list(entity_config.fields.keys()),
        ))

    # Limit validation
    limit = arguments.get("limit", 50)
    if not isinstance(limit, int) or limit < 1:
        errors.append(_error("INVALID_VALUE", "limit", "Limit must be a positive integer"))
    elif limit > 200:
        errors.append(_error("INVALID_VALUE", "limit", "Maximum limit is 200"))

    if errors:
        return {"error": True, "code": "VALIDATION_ERROR", "errors": errors}

    return None


def validate_aggregate_input(arguments: dict[str, Any]) -> Optional[dict]:
    """
    Validate input for the aggregate tool.
    Returns error dict if invalid, None if valid.
    """
    errors = []

    # Entity validation
    entity = arguments.get("entity")
    if not entity:
        errors.append(_error("MISSING_ENTITY", "entity", "Entity is required", validEntities=get_entity_names()))
    elif entity not in ENTITIES:
        errors.append(_error("UNKNOWN_ENTITY", "entity", f"Unknown entity '{entity}'", validEntities=get_entity_names()))

    if errors:
        return {"error": True, "code": "VALIDATION_ERROR", "errors": errors}

    entity_config = ENTITIES[entity]

    # Where validation (same as query)
    where = arguments.get("where", {})
    if where:
        for field_name, operators in where.items():
            if "." in field_name:
                _validate_dot_notation(entity, entity_config, field_name, errors)
            elif field_name not in entity_config.fields:
                errors.append(_error(
                    "UNKNOWN_FIELD", f"where.{field_name}",
                    f"Unknown field '{field_name}' on entity '{entity}'",
                    validFields=list(entity_config.fields.keys()),
                ))

    # Aggregate validation
    aggregate = arguments.get("aggregate", {})
    if aggregate:
        for func, field_name in aggregate.items():
            if func not in VALID_AGGREGATE_FUNCS:
                errors.append(_error(
                    "INVALID_OPERATOR", f"aggregate.{func}",
                    f"Unknown aggregate function '{func}'",
                    validFunctions=list(VALID_AGGREGATE_FUNCS),
                ))
            # count is a boolean, doesn't reference a field
            if func != "count" and isinstance(field_name, str) and field_name not in entity_config.fields:
                errors.append(_error(
                    "UNKNOWN_FIELD", f"aggregate.{func}",
                    f"Cannot aggregate on unknown field '{field_name}'",
                    validFields=list(entity_config.fields.keys()),
                ))

    # GroupBy validation
    group_by = arguments.get("groupBy", [])
    if group_by:
        for field_name in group_by:
            if field_name not in entity_config.fields:
                errors.append(_error(
                    "UNKNOWN_FIELD", f"groupBy.{field_name}",
                    f"Cannot group by unknown field '{field_name}'",
                    validFields=list(entity_config.fields.keys()),
                ))

    if errors:
        return {"error": True, "code": "VALIDATION_ERROR", "errors": errors}

    return None
