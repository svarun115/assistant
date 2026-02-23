"""
Health Tracking MCP Tools
Specialized tools for logging illnesses, injuries, medicines, and supplements.
"""

from mcp import types


def get_health_tools() -> list[types.Tool]:
    """
    Returns write tools for health tracking.

    Tools included:
    - log_health_condition: Log illness or injury
    - log_medicine: Log medicine taken
    - log_supplement: Log dietary supplement taken
    - update_health_condition: Update health condition entries
    - update_medicine: Update medicine log entries
    - update_supplement: Update supplement log entries
    - log_health_condition_update: Log a progression update for a condition
    - update_health_condition_log: Update a progression log entry

    Delete: use delete_entity with entity_type "health_condition", "medicine",
    "supplement", or "health_condition_log" (no restore supported for health entities).
    For querying health data, use execute_sql_query instead (SQL-first architecture).
    """
    return [
        _log_health_condition_tool(),
        _log_medicine_tool(),
        _log_supplement_tool(),
        _log_health_condition_update_tool(),
        _update_health_condition_tool(),
        _update_medicine_tool(),
        _update_supplement_tool(),
        _update_health_condition_log_tool(),
    ]


def _log_health_condition_tool() -> types.Tool:
    """Log a health condition (illness or injury) with event linkage."""
    return types.Tool(
        name="log_health_condition",
        description="""Log a health condition (illness or injury) with event linkage.

Creates a health condition entry linked to an event. Health conditions:
- Can span multiple days (use start_date and end_date)
- Support severity tracking (hospitalized, clinic visit, doc consultation, home remedy, mild, moderate, severe)
- Support 1-10 severity scoring
- Track sport-related injuries
- Track conditions for any person (defaults to owner if not specified)

Use person_id parameter to track conditions for family members (spouse, children, parents, etc.)

EXAMPLE (tracking own condition):
{
  "condition_type": "illness",
  "condition_name": "flu",
  "severity": "home_remedy",
  "severity_score": 6,
  "start_date": "2025-10-15",
  "end_date": "2025-10-17",
  "notes": "Recovering well with rest and fluids"
}

EXAMPLE (tracking family member's condition):
{
  "condition_type": "injury",
  "condition_name": "MCL strain",
  "person_id": "<spouse-uuid>",
  "severity": "moderate",
  "severity_score": 7,
  "is_sport_related": true,
  "sport_type": "skiing",
  "start_date": "2026-01-15",
  "notes": "Skiing injury, suspected MCL/meniscus"
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "condition_type": {
                    "type": "string",
                    "enum": ["illness", "injury"],
                    "description": "Type of health condition"
                },
                "condition_name": {
                    "type": "string",
                    "description": "Name of condition (e.g., 'headache', 'flu', 'broken_arm')"
                },
                "person_id": {
                    "type": "string",
                    "description": "Optional UUID of the person affected. If not provided, defaults to owner. Use this to track conditions for family members (spouse, children, parents, etc.)"
                },
                "severity": {
                    "type": "string",
                    "enum": ["hospitalized", "clinic_visit", "doc_consultation", "home_remedy", "mild", "moderate", "severe"],
                    "description": "Severity level"
                },
                "severity_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Pain/severity score (1-10)"
                },
                "is_sport_related": {
                    "type": "boolean",
                    "description": "Is this injury sport-related? (only for injuries)",
                    "default": False
                },
                "sport_type": {
                    "type": "string",
                    "description": "Sport type if injury_sport_related (e.g., 'soccer', 'running', 'skiing')"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date (ISO 8601: YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (ISO 8601: YYYY-MM-DD) - leave null if ongoing"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            },
            "required": ["condition_type", "condition_name", "start_date"]
        }
    )


def _log_medicine_tool() -> types.Tool:
    """Log medicine taken (optionally linked to a condition or event)."""
    return types.Tool(
        name="log_medicine",
        description="""Log medicine taken (optionally linked to a condition or event).

Create a medicine log entry. Can be:
- Standalone (just tracking what was taken)
- Linked to a health condition (e.g., ibuprofen for headache)
- Linked to an event (e.g., took aspirin at a specific time)

EXAMPLE:
{
  "medicine_name": "ibuprofen",
  "dosage": "500",
  "dosage_unit": "mg",
  "frequency": "every 6 hours",
  "log_date": "2025-10-15",
  "log_time": "14:30:00",
  "notes": "For post-workout soreness"
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "medicine_name": {
                    "type": "string",
                    "description": "Name of medicine (e.g., 'ibuprofen', 'aspirin', 'amoxicillin')"
                },
                "dosage": {
                    "type": "string",
                    "description": "Dosage amount (e.g., '500', '1')"
                },
                "dosage_unit": {
                    "type": "string",
                    "description": "Unit of dosage (e.g., 'mg', 'tablet', 'capsule', 'ml')"
                },
                "frequency": {
                    "type": "string",
                    "description": "How often taken (e.g., 'once daily', 'every 6 hours', 'as needed')"
                },
                "condition_id": {
                    "type": "string",
                    "description": "UUID of related health condition (optional)"
                },
                "event_id": {
                    "type": "string",
                    "description": "UUID of related event (optional)"
                },
                "log_date": {
                    "type": "string",
                    "description": "Date medicine was taken (ISO 8601: YYYY-MM-DD)"
                },
                "log_time": {
                    "type": "string",
                    "description": "Time medicine was taken (ISO 8601: HH:MM:SS, optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            },
            "required": ["medicine_name", "log_date"]
        }
    )


def _log_supplement_tool() -> types.Tool:
    """Log dietary supplement taken (routine wellness logging)."""
    return types.Tool(
        name="log_supplement",
        description="""Log dietary supplement taken (routine wellness logging).

Create a supplement log entry for daily wellness tracking. Useful for:
- Vitamins (Vitamin D, multivitamin, etc.)
- Minerals (zinc, magnesium, etc.)
- Proteins and amino acids
- Other dietary supplements

EXAMPLE:
{
  "supplement_name": "vitamin_d",
  "amount": "1000",
  "amount_unit": "iu",
  "frequency": "daily",
  "log_date": "2025-10-15",
  "log_time": "09:00:00",
  "notes": "Morning routine"
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "supplement_name": {
                    "type": "string",
                    "description": "Name of supplement (e.g., 'multivitamin', 'vitamin_d', 'protein', 'creatine', 'zinc', 'magnesium')"
                },
                "amount": {
                    "type": "string",
                    "description": "Amount taken (e.g., '1000', '2', '1 scoop')"
                },
                "amount_unit": {
                    "type": "string",
                    "description": "Unit of amount (e.g., 'mg', 'iu', 'grams', 'scoops', 'capsules', 'tablets')"
                },
                "frequency": {
                    "type": "string",
                    "description": "How often taken (e.g., 'daily', 'every other day', 'twice daily')"
                },
                "event_id": {
                    "type": "string",
                    "description": "UUID of related event (optional)"
                },
                "log_date": {
                    "type": "string",
                    "description": "Date supplement was taken (ISO 8601: YYYY-MM-DD)"
                },
                "log_time": {
                    "type": "string",
                    "description": "Time supplement was taken (ISO 8601: HH:MM:SS, optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            },
            "required": ["supplement_name", "log_date"]
        }
    )


def _update_health_condition_tool() -> types.Tool:
    """Update existing health condition entry."""
    return types.Tool(
        name="update_health_condition",
        description="Update existing health condition entry. Use this to update severity, add end dates, or modify notes. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "condition_id": {
                    "type": "string",
                    "description": "UUID of the health condition to update (from get_recent_conditions)"
                },
                "condition_name": {
                    "type": "string",
                    "description": "Updated condition name (optional)"
                },
                "severity": {
                    "type": "string",
                    "enum": ["hospitalized", "clinic_visit", "doc_consultation", "home_remedy", "mild", "moderate", "severe"],
                    "description": "Updated severity level (optional)"
                },
                "severity_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Updated severity score (1-10, optional)"
                },
                "end_date": {
                    "type": "string",
                    "description": "Updated end date (ISO 8601: YYYY-MM-DD, optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                }
            },
            "required": ["condition_id"]
        }
    )


def _update_medicine_tool() -> types.Tool:
    """Update existing medicine log entry."""
    return types.Tool(
        name="update_medicine",
        description="Update existing medicine log entry. Use this to correct dosages, frequencies, or notes. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "medicine_id": {
                    "type": "string",
                    "description": "UUID of the medicine log to update (from get_recent_medicines)"
                },
                "medicine_name": {
                    "type": "string",
                    "description": "Updated medicine name (optional)"
                },
                "dosage": {
                    "type": "string",
                    "description": "Updated dosage amount (optional)"
                },
                "dosage_unit": {
                    "type": "string",
                    "description": "Updated dosage unit (optional)"
                },
                "frequency": {
                    "type": "string",
                    "description": "Updated frequency (optional)"
                },
                "log_date": {
                    "type": "string",
                    "description": "Updated date (ISO 8601: YYYY-MM-DD, optional)"
                },
                "log_time": {
                    "type": "string",
                    "description": "Updated time (ISO 8601: HH:MM:SS, optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                }
            },
            "required": ["medicine_id"]
        }
    )


def _update_supplement_tool() -> types.Tool:
    """Update existing supplement log entry."""
    return types.Tool(
        name="update_supplement",
        description="Update existing supplement log entry. Use this to correct amounts, frequencies, or notes. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "supplement_id": {
                    "type": "string",
                    "description": "UUID of the supplement log to update (from get_recent_supplements)"
                },
                "supplement_name": {
                    "type": "string",
                    "description": "Updated supplement name (optional)"
                },
                "amount": {
                    "type": "string",
                    "description": "Updated amount (optional)"
                },
                "amount_unit": {
                    "type": "string",
                    "description": "Updated amount unit (optional)"
                },
                "frequency": {
                    "type": "string",
                    "description": "Updated frequency (optional)"
                },
                "log_date": {
                    "type": "string",
                    "description": "Updated date (ISO 8601: YYYY-MM-DD, optional)"
                },
                "log_time": {
                    "type": "string",
                    "description": "Updated time (ISO 8601: HH:MM:SS, optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                }
            },
            "required": ["supplement_id"]
        }
    )


def _log_health_condition_update_tool() -> types.Tool:
    """Log a progression update for an existing health condition."""
    return types.Tool(
        name="log_health_condition_update",
        description="""Log a progression update for an existing health condition. Creates a daily snapshot of severity for tracking improvement or worsening over time.

One log entry per condition per day (unique constraint). Use this to track how an illness or injury progresses.

EXAMPLE:
{
  "condition_id": "uuid-of-condition",
  "log_date": "2026-02-11",
  "severity": "mild",
  "severity_score": 3,
  "notes": "Much better today, only slight discomfort"
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "condition_id": {
                    "type": "string",
                    "description": "UUID of the health condition to log progression for"
                },
                "log_date": {
                    "type": "string",
                    "description": "Date of this update (YYYY-MM-DD)"
                },
                "severity": {
                    "type": "string",
                    "description": "Severity level",
                    "enum": ["hospitalized", "clinic_visit", "doc_consultation", "home_remedy", "mild", "moderate", "severe"]
                },
                "severity_score": {
                    "type": "integer",
                    "description": "Pain/severity score (1-10)",
                    "minimum": 1,
                    "maximum": 10
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about condition status on this day"
                }
            },
            "required": ["condition_id", "log_date"]
        }
    )


def _update_health_condition_log_tool() -> types.Tool:
    """Update an existing health condition log entry."""
    return types.Tool(
        name="update_health_condition_log",
        description="Update an existing health condition progression log entry. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "log_id": {
                    "type": "string",
                    "description": "UUID of the log entry to update"
                },
                "severity": {
                    "type": "string",
                    "description": "Updated severity level",
                    "enum": ["hospitalized", "clinic_visit", "doc_consultation", "home_remedy", "mild", "moderate", "severe"]
                },
                "severity_score": {
                    "type": "integer",
                    "description": "Updated severity score (1-10)",
                    "minimum": 1,
                    "maximum": 10
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes"
                },
                "log_date": {
                    "type": "string",
                    "description": "Updated date (YYYY-MM-DD)"
                }
            },
            "required": ["log_id"]
        }
    )



