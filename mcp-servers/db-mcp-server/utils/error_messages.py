"""
Error Message Utilities

Provides human-readable error messages for database constraint violations
and enum validation errors. (Issues #101, #102)
"""

import re
from typing import Optional

# Valid enum values for common types
ENUM_VALUES = {
    "event_category_enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
    "event_type_enum": ["sleep", "reflection", "work", "generic"],
    "significance_enum": ["routine", "notable", "major_milestone"],
    "workout_category_enum": ["STRENGTH", "CARDIO", "FLEXIBILITY", "SPORTS", "MIXED"],
    "workout_subtype_enum": ["GYM_STRENGTH", "GYM_CARDIO", "RUN", "SWIM", "BIKE", "HIKE", "SPORT", "YOGA", "CROSSFIT", "CALISTHENICS", "DANCE", "MARTIAL_ARTS", "OTHER"],
    "set_type_enum": ["WARMUP", "WORKING", "DROP", "FAILURE"],
    "transport_mode_enum": ["driving", "public_transit", "walking", "cycling", "running", "flying", "rideshare", "taxi", "train", "bus", "subway", "ferry", "scooter", "other"],
    "relationship_type_enum": ["parent", "child", "sibling", "spouse", "cousin", "grandparent", "grandchild", "aunt_uncle", "niece_nephew", "other"],
    "entertainment_type_enum": ["movie", "tv_show", "video", "podcast", "live_performance", "gaming", "reading", "streaming", "concert", "theater", "sports_event", "other"],
    "meal_type_enum": ["breakfast", "brunch", "lunch", "dinner", "snack", "dessert", "beverage", "other"],
    "portion_size_enum": ["small", "medium", "large", "extra_large"],
}

# Human-readable constraint explanations
CONSTRAINT_MESSAGES = {
    "check_reps_or_interval": (
        "Sets must have either 'reps' or 'interval_description' specified. "
        "For rep-based exercises, use 'reps'. For interval-based exercises (Tabata, HIIT), use 'interval_description'."
    ),
    "check_valid_dates": "End date must be after start date.",
    "check_valid_time_period": "End time must be after start time.",
    "check_intensity_range": "Intensity must be between 1 and 10.",
    "check_positive_weight": "Weight must be a positive number.",
    "check_positive_reps": "Reps must be a positive number.",
    "check_positive_duration": "Duration must be a positive number.",
    "events_pkey": "An event with this ID already exists.",
    "people_pkey": "A person with this ID already exists.",
    "locations_pkey": "A location with this ID already exists.",
    "workouts_pkey": "A workout with this ID already exists.",
}


def enhance_error_message(error: Exception) -> str:
    """
    Enhance database error messages with human-readable explanations.
    
    Handles:
    - Invalid enum values (adds list of valid values)
    - Constraint violations (adds explanation of the constraint)
    - Foreign key violations (explains the relationship)
    
    Returns the enhanced error message string.
    """
    error_str = str(error)
    
    # Check for enum validation errors
    enum_match = re.search(r'invalid input value for enum (\w+): "([^"]+)"', error_str)
    if enum_match:
        enum_name = enum_match.group(1)
        invalid_value = enum_match.group(2)
        valid_values = ENUM_VALUES.get(enum_name, [])
        
        if valid_values:
            return (
                f"Invalid value '{invalid_value}' for {enum_name}. "
                f"Valid values: {', '.join(valid_values)}"
            )
    
    # Check for constraint violations
    constraint_match = re.search(r'violates check constraint "(\w+)"', error_str)
    if constraint_match:
        constraint_name = constraint_match.group(1)
        explanation = CONSTRAINT_MESSAGES.get(constraint_name)
        
        if explanation:
            return f"Constraint violation ({constraint_name}): {explanation}"
        else:
            # Return original with constraint name highlighted
            return f"Constraint violation: {constraint_name}. {error_str}"
    
    # Check for foreign key violations
    fk_match = re.search(r'violates foreign key constraint "(\w+)"', error_str)
    if fk_match:
        constraint_name = fk_match.group(1)
        return (
            f"Foreign key violation ({constraint_name}): "
            f"The referenced record does not exist. {error_str}"
        )
    
    # Check for unique constraint violations
    unique_match = re.search(r'duplicate key value violates unique constraint "(\w+)"', error_str)
    if unique_match:
        constraint_name = unique_match.group(1)
        return f"Duplicate entry: A record with this value already exists ({constraint_name})."
    
    # Check for not-null violations
    null_match = re.search(r'null value in column "(\w+)" .* violates not-null constraint', error_str)
    if null_match:
        column_name = null_match.group(1)
        return f"Required field missing: '{column_name}' cannot be null."
    
    # Return original error if no enhancement found
    return error_str


def get_enum_values(enum_name: str) -> Optional[list]:
    """Get valid values for a known enum type."""
    return ENUM_VALUES.get(enum_name)


def format_enum_hint(enum_name: str) -> str:
    """Format a hint string showing valid enum values."""
    values = ENUM_VALUES.get(enum_name, [])
    if values:
        return f"Valid values for {enum_name}: {', '.join(values)}"
    return ""
