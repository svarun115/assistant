"""
Entity Configuration Registry

Maps domain field names to actual database columns, defines relationships,
and configures soft-delete behavior for each queryable entity.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldDef:
    """Maps a domain field name to a database column."""
    column: str
    type: str  # uuid, string, integer, float, timestamp, date, enum, array, boolean
    is_expression: bool = False  # True if column is a SQL expression (e.g. DATE(start_time))


@dataclass
class RelationshipDef:
    """Defines how one entity relates to another."""
    type: str  # belongs_to, has_one, has_many, many_through
    target_entity: str
    local_key: str  # Column on this entity
    target_key: str  # Column on target entity
    through_table: Optional[str] = None  # For many_through
    through_local: Optional[str] = None  # Junction table FK to this entity
    through_target: Optional[str] = None  # Junction table FK to target entity
    extra_fields: list[str] = field(default_factory=list)  # Extra columns from junction table


@dataclass
class SoftDeleteConfig:
    """Configures soft-delete filtering for an entity."""
    flag_column: str = "is_deleted"
    timestamp_column: str = "deleted_at"


@dataclass
class EntityConfig:
    """Complete configuration for a queryable entity."""
    table: str
    fields: dict[str, FieldDef]
    relationships: dict[str, RelationshipDef] = field(default_factory=dict)
    soft_delete: Optional[SoftDeleteConfig] = None
    default_order: str = "created_at DESC"
    table_alias: str = ""  # Auto-set if empty

    def __post_init__(self):
        if not self.table_alias:
            self.table_alias = self.table[0]  # First letter as default alias


# =============================================================================
# Entity Registry
# =============================================================================

ENTITIES: dict[str, EntityConfig] = {
    "events": EntityConfig(
        table="events",
        table_alias="e",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "type": FieldDef(column="event_type", type="enum"),
            "title": FieldDef(column="title", type="string"),
            "description": FieldDef(column="description", type="string"),
            "date": FieldDef(column="DATE(start_time)", type="date", is_expression=True),
            "start": FieldDef(column="start_time", type="timestamp"),
            "end": FieldDef(column="end_time", type="timestamp"),
            "duration": FieldDef(column="duration_minutes", type="integer"),
            "location_id": FieldDef(column="location_id", type="uuid"),
            "category": FieldDef(column="category", type="enum"),
            "significance": FieldDef(column="significance", type="enum"),
            "notes": FieldDef(column="notes", type="string"),
            "tags": FieldDef(column="tags", type="array"),
        },
        relationships={
            "participants": RelationshipDef(
                type="many_through",
                through_table="event_participants",
                target_entity="people",
                local_key="id",
                through_local="event_id",
                through_target="person_id",
                target_key="id",
                extra_fields=["role", "interaction_mode"],
            ),
            "location": RelationshipDef(
                type="belongs_to",
                target_entity="locations",
                local_key="location_id",
                target_key="id",
            ),
            "workout": RelationshipDef(
                type="has_one",
                target_entity="workouts",
                local_key="id",
                target_key="event_id",
            ),
            "meal": RelationshipDef(
                type="has_one",
                target_entity="meals",
                local_key="id",
                target_key="event_id",
            ),
            "commute": RelationshipDef(
                type="has_one",
                target_entity="commutes",
                local_key="id",
                target_key="event_id",
            ),
            "entertainment": RelationshipDef(
                type="has_one",
                target_entity="entertainment",
                local_key="id",
                target_key="event_id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="start_time DESC",
    ),

    "people": EntityConfig(
        table="people",
        table_alias="p",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "name": FieldDef(column="canonical_name", type="string"),
            "aliases": FieldDef(column="aliases", type="array"),
            "relationship": FieldDef(column="relationship", type="enum"),
            "category": FieldDef(column="category", type="enum"),
            "kinship": FieldDef(column="kinship_to_owner", type="string"),
            "birthday": FieldDef(column="birthday", type="string"),
            "known_since": FieldDef(column="known_since", type="string"),
            "last_interaction": FieldDef(column="last_interaction_date", type="string"),
        },
        relationships={
            "relationships": RelationshipDef(
                type="many_through",
                through_table="person_relationships",
                target_entity="people",
                local_key="id",
                through_local="person_id",
                through_target="related_person_id",
                target_key="id",
                extra_fields=["relationship_type", "relationship_label"],
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="canonical_name ASC",
    ),

    "locations": EntityConfig(
        table="locations",
        table_alias="l",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "name": FieldDef(column="canonical_name", type="string"),
            "type": FieldDef(column="location_type", type="enum"),
            "place_id": FieldDef(column="place_id", type="string"),
            "notes": FieldDef(column="notes", type="string"),
        },
        relationships={},
        soft_delete=SoftDeleteConfig(),
        default_order="canonical_name ASC",
    ),

    "exercises": EntityConfig(
        table="exercises",
        table_alias="ex",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "name": FieldDef(column="canonical_name", type="string"),
            "category": FieldDef(column="category", type="enum"),
            "muscle_group": FieldDef(column="primary_muscle_group", type="string"),
            "secondary_muscles": FieldDef(column="secondary_muscle_groups", type="array"),
            "equipment": FieldDef(column="equipment", type="array"),
            "variants": FieldDef(column="variants", type="array"),
            "notes": FieldDef(column="notes", type="string"),
        },
        relationships={},
        soft_delete=SoftDeleteConfig(),
        default_order="canonical_name ASC",
    ),

    "journal_entries": EntityConfig(
        table="journal_entries",
        table_alias="j",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "date": FieldDef(column="entry_date", type="date"),
            "type": FieldDef(column="entry_type", type="enum"),
            "text": FieldDef(column="raw_text", type="string"),
            "tags": FieldDef(column="tags", type="array"),
        },
        relationships={},
        soft_delete=SoftDeleteConfig(),
        default_order="entry_date DESC",
    ),

    "workouts": EntityConfig(
        table="workouts",
        table_alias="w",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "event_id": FieldDef(column="event_id", type="uuid"),
            "name": FieldDef(column="workout_name", type="string"),
            "category": FieldDef(column="category", type="enum"),
            "subtype": FieldDef(column="workout_subtype", type="enum"),
            "sport_type": FieldDef(column="sport_type", type="string"),
        },
        relationships={
            "event": RelationshipDef(
                type="belongs_to",
                target_entity="events",
                local_key="event_id",
                target_key="id",
            ),
            "exercises": RelationshipDef(
                type="has_many",
                target_entity="_workout_exercises",
                local_key="id",
                target_key="workout_id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="created_at DESC",
    ),

    # Internal entity for workout exercise hydration (not directly queryable)
    "_workout_exercises": EntityConfig(
        table="workout_exercises",
        table_alias="we",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "workout_id": FieldDef(column="workout_id", type="uuid"),
            "exercise_id": FieldDef(column="exercise_id", type="uuid"),
            "sequence_order": FieldDef(column="sequence_order", type="integer"),
            "notes": FieldDef(column="notes", type="string"),
        },
        relationships={
            "exercise": RelationshipDef(
                type="belongs_to",
                target_entity="exercises",
                local_key="exercise_id",
                target_key="id",
            ),
            "sets": RelationshipDef(
                type="has_many",
                target_entity="_exercise_sets",
                local_key="id",
                target_key="workout_exercise_id",
            ),
        },
        soft_delete=None,  # No soft delete on junction table
        default_order="sequence_order ASC",
    ),

    # Internal entity for exercise set hydration (not directly queryable)
    "_exercise_sets": EntityConfig(
        table="exercise_sets",
        table_alias="es",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "workout_exercise_id": FieldDef(column="workout_exercise_id", type="uuid"),
            "set_number": FieldDef(column="set_number", type="integer"),
            "set_type": FieldDef(column="set_type", type="enum"),
            "weight_kg": FieldDef(column="weight_kg", type="float"),
            "reps": FieldDef(column="reps", type="integer"),
            "duration_s": FieldDef(column="duration_s", type="integer"),
            "distance_km": FieldDef(column="distance_km", type="float"),
            "rest_time_s": FieldDef(column="rest_time_s", type="integer"),
            "pace": FieldDef(column="pace", type="string"),
            "volume_kg": FieldDef(column="volume_kg", type="float"),
            "notes": FieldDef(column="notes", type="string"),
        },
        relationships={},
        soft_delete=None,
        default_order="set_number ASC",
    ),

    "meals": EntityConfig(
        table="meals",
        table_alias="m",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "event_id": FieldDef(column="event_id", type="uuid"),
            "meal_title": FieldDef(column="meal_title", type="enum"),
            "meal_type": FieldDef(column="meal_type", type="enum"),
            "portion_size": FieldDef(column="portion_size", type="enum"),
        },
        relationships={
            "event": RelationshipDef(
                type="belongs_to",
                target_entity="events",
                local_key="event_id",
                target_key="id",
            ),
            "items": RelationshipDef(
                type="has_many",
                target_entity="_meal_items",
                local_key="id",
                target_key="meal_id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="created_at DESC",
    ),

    # Internal entity for meal item hydration
    "_meal_items": EntityConfig(
        table="meal_items",
        table_alias="mi",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "meal_id": FieldDef(column="meal_id", type="uuid"),
            "item_name": FieldDef(column="item_name", type="string"),
            "quantity": FieldDef(column="quantity", type="string"),
        },
        relationships={},
        soft_delete=None,
        default_order="created_at ASC",
    ),

    "commutes": EntityConfig(
        table="commutes",
        table_alias="c",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "event_id": FieldDef(column="event_id", type="uuid"),
            "from_location_id": FieldDef(column="from_location_id", type="uuid"),
            "to_location_id": FieldDef(column="to_location_id", type="uuid"),
            "transport_mode": FieldDef(column="transport_mode", type="enum"),
        },
        relationships={
            "event": RelationshipDef(
                type="belongs_to",
                target_entity="events",
                local_key="event_id",
                target_key="id",
            ),
            "from_location": RelationshipDef(
                type="belongs_to",
                target_entity="locations",
                local_key="from_location_id",
                target_key="id",
            ),
            "to_location": RelationshipDef(
                type="belongs_to",
                target_entity="locations",
                local_key="to_location_id",
                target_key="id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="created_at DESC",
    ),

    "entertainment": EntityConfig(
        table="entertainment",
        table_alias="ent",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "event_id": FieldDef(column="event_id", type="uuid"),
            "entertainment_type": FieldDef(column="entertainment_type", type="enum"),
            "title": FieldDef(column="title", type="string"),
            "creator": FieldDef(column="creator", type="string"),
            "genre": FieldDef(column="genre", type="string"),
            "show_name": FieldDef(column="show_name", type="string"),
            "season": FieldDef(column="season_number", type="integer"),
            "episode": FieldDef(column="episode_number", type="integer"),
            "episode_title": FieldDef(column="episode_title", type="string"),
            "channel": FieldDef(column="channel_name", type="string"),
            "director": FieldDef(column="director", type="string"),
            "release_year": FieldDef(column="release_year", type="integer"),
            "platform": FieldDef(column="platform", type="string"),
            "rating": FieldDef(column="personal_rating", type="integer"),
            "completion": FieldDef(column="completion_status", type="enum"),
            "rewatch": FieldDef(column="rewatch", type="boolean"),
        },
        relationships={
            "event": RelationshipDef(
                type="belongs_to",
                target_entity="events",
                local_key="event_id",
                target_key="id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="created_at DESC",
    ),

    "reflections": EntityConfig(
        table="reflections",
        table_alias="r",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "event_id": FieldDef(column="event_id", type="uuid"),
            "reflection_type": FieldDef(column="reflection_type", type="enum"),
            "mood": FieldDef(column="mood", type="string"),
            "mood_score": FieldDef(column="mood_score", type="integer"),
            "prompt": FieldDef(column="prompt_question", type="string"),
            "insights": FieldDef(column="key_insights", type="array"),
            "action_items": FieldDef(column="action_items", type="array"),
        },
        relationships={
            "event": RelationshipDef(
                type="belongs_to",
                target_entity="events",
                local_key="event_id",
                target_key="id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="created_at DESC",
    ),

    "health_conditions": EntityConfig(
        table="health_conditions",
        table_alias="hc",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "event_id": FieldDef(column="event_id", type="uuid"),
            "condition_type": FieldDef(column="condition_type", type="enum"),
            "condition_name": FieldDef(column="condition_name", type="string"),
            "severity": FieldDef(column="severity", type="enum"),
            "severity_score": FieldDef(column="severity_score", type="integer"),
            "is_sport_related": FieldDef(column="is_sport_related", type="boolean"),
            "sport_type": FieldDef(column="sport_type", type="string"),
            "start_date": FieldDef(column="start_date", type="date"),
            "end_date": FieldDef(column="end_date", type="date"),
            "notes": FieldDef(column="notes", type="string"),
        },
        relationships={
            "event": RelationshipDef(
                type="belongs_to",
                target_entity="events",
                local_key="event_id",
                target_key="id",
            ),
            "logs": RelationshipDef(
                type="has_many",
                target_entity="health_condition_logs",
                local_key="id",
                target_key="condition_id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="start_date DESC",
    ),

    "health_condition_logs": EntityConfig(
        table="health_condition_logs",
        table_alias="hcl",
        fields={
            "id": FieldDef(column="id", type="uuid"),
            "condition_id": FieldDef(column="condition_id", type="uuid"),
            "log_date": FieldDef(column="log_date", type="date"),
            "severity": FieldDef(column="severity", type="enum"),
            "severity_score": FieldDef(column="severity_score", type="integer"),
            "notes": FieldDef(column="notes", type="string"),
        },
        relationships={
            "condition": RelationshipDef(
                type="belongs_to",
                target_entity="health_conditions",
                local_key="condition_id",
                target_key="id",
            ),
        },
        soft_delete=SoftDeleteConfig(),
        default_order="log_date DESC",
    ),
}

# Public entity names (excludes internal _prefixed entities)
PUBLIC_ENTITIES = [name for name in ENTITIES if not name.startswith("_")]


def get_entity_config(entity_name: str) -> Optional[EntityConfig]:
    """Get entity config by name, or None if not found."""
    return ENTITIES.get(entity_name)


def get_entity_names() -> list[str]:
    """Get list of all publicly queryable entity names."""
    return PUBLIC_ENTITIES
