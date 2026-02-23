"""
Structured Query Language for Journal MCP Server

Replaces raw SQL reads with a typed, validated query interface.
Gated behind QUERY_MODE=structured env var.
"""

from .entities import ENTITIES, get_entity_config
from .builder import QueryBuilder
from .hydrator import Hydrator
from .validators import validate_query_input, validate_aggregate_input

__all__ = [
    'ENTITIES',
    'get_entity_config',
    'QueryBuilder',
    'Hydrator',
    'validate_query_input',
    'validate_aggregate_input',
]
