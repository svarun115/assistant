"""
People Management MCP Tools
Domain-specific tools for managing people, relationships, and biographical information.
"""

from mcp import types


def get_people_tools() -> list[types.Tool]:
    """
    Returns people management write tools (CRUD operations).

    Tools included:
    - create_person: Create person with biographical details
    - add_person_note: Add biographical notes/observations
    - add_person_relationship: Define family/social connections
    - update_person: Update existing person fields
    - update_person_relationship: Update relationship label/notes
    - add_person_work: Add employment history
    - add_person_education: Add education history
    - add_person_residence: Add residence history
    - update_person_work: Update work history (dates, company, role)
    - update_person_education: Update education history (dates, institution, degree)
    - update_person_residence: Update residence history (dates, location)
    - update_person_note: Update biographical notes
    - merge_duplicate_people: Merge duplicate person records

    Delete/restore: use delete_entity / restore_entity with entity_type="person",
    "person_relationship", or "person_residence".
    For querying/searching people, use execute_sql_query instead.
    """
    return [
        _create_person_tool(),
        _add_person_note_tool(),
        _add_person_relationship_tool(),
        _update_person_tool(),
        _update_person_relationship_tool(),
        _add_person_work_tool(),
        _add_person_education_tool(),
        _add_person_residence_tool(),
        _update_person_work_tool(),
        _update_person_education_tool(),
        _update_person_residence_tool(),
        _update_person_note_tool(),
        _merge_duplicate_people_tool(),
    ]

# Individual tool definitions
def _create_person_tool() -> types.Tool:
    return types.Tool(
        name="create_person",
        description="Create a new person with comprehensive biographical details. Use this to manually create a person entry (not just auto-created via events). Supports full biographical data including name, aliases, relationships, birthday, ethnicity, origin, interaction history, and optional Google People API link for contact information.",
        inputSchema={
            "type": "object",
            "properties": {
                "canonical_name": {
                    "type": "string",
                    "description": "Primary name you use for this person (required)"
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Nicknames, alternate names, or alternate spellings (optional)"
                },
                "relationship": {
                    "type": "string",
                    "enum": ["friend", "family", "colleague", "partner", "acquaintance", "mentor", "mentee", "other"],
                    "description": "Type of relationship (optional)"
                },
                "category": {
                    "type": "string",
                    "enum": ["close_friend", "friend", "acquaintance", "family", "work", "not_met", "other"],
                    "description": "Closeness/organizational category (optional)"
                },
                "kinship_to_owner": {
                    "type": "string",
                    "description": "Specific kinship relation to the owner (e.g., 'mother', 'father', 'brother', 'sister', 'son', 'daughter') (optional)"
                },
                "birthday": {
                    "type": "string",
                    "description": "Birthday as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional). Must match one of these formats."
                },
                "death_date": {
                    "type": "string",
                    "description": "Date of death as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional). Must match one of these formats."
                },
                "ethnicity": {
                    "type": "string",
                    "description": "Ethnicity or cultural background (optional)"
                },
                "origin_location": {
                    "type": "string",
                    "description": "Place of origin, hometown (optional)"
                },
                "known_since": {
                    "type": "string",
                    "description": "Year or date you first met this person (optional). Must be partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD."
                },
                "last_interaction_date": {
                    "type": "string",
                    "description": "Most recent interaction as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)."
                },
                "google_people_id": {
                    "type": "string",
                    "description": "Google People API resource ID for this contact (e.g., 'people/c1234567890'). Links person to Google Contacts for automatic contact info and social profiles (optional)."
                }
            },
            "required": ["canonical_name"]
        }
    )


def _add_person_note_tool() -> types.Tool:
    return types.Tool(
        name="add_person_note",
        description="Add a biographical note or observation about a person. Use this to record health information, personality traits, interests, stories, achievements, preferences, or any biographical details. Supports categorization, tagging, and source tracking.",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the person (use search_people to find)"
                },
                "text": {
                    "type": "string",
                    "description": "The biographical note text (required)"
                },
                "note_type": {
                    "type": "string",
                    "enum": ["biographical", "health", "preference", "interest", "story", "personality", "achievement", "other"],
                    "description": "How the information is characterized (optional)"
                },
                "category": {
                    "type": "string",
                    "enum": ["health", "personality", "hobbies", "family", "career", "preferences", "beliefs", "achievements", "stories", "other"],
                    "description": "What domain the information belongs to (optional)"
                },
                "note_date": {
                    "type": "string",
                    "description": "Date the note relates to in YYYY-MM-DD format (optional)"
                },
                "source": {
                    "type": "string",
                    "enum": ["conversation", "observation", "social_media", "told_by_others", "inference", "document", "other"],
                    "description": "How you obtained this information (optional)"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context about the note (optional)"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization (optional)"
                }
            },
            "required": ["person_id", "text"]
        }
    )


def _add_person_relationship_tool() -> types.Tool:
    return types.Tool(
        name="add_person_relationship",
        description="Define a relationship between two people (family tree, social connections, work relationships). Supports automatic bidirectional relationship creation - when you create 'parent', the reverse 'child' relationship is automatically created. For family relationships use relationship_type enum (parent, child, sibling, spouse, etc.). For non-family relationships like work connections, use relationship_type='other' and specify relationship_label (e.g., 'manager', 'direct report', 'mentor', 'colleague').",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the first person"
                },
                "related_person_id": {
                    "type": "string",
                    "description": "UUID of the related person"
                },
                "relationship_type": {
                    "type": "string",
                    "enum": ["parent", "child", "sibling", "spouse", "cousin", "grandparent", "grandchild", "aunt_uncle", "niece_nephew", "other"],
                    "description": "Type of relationship from person_id's perspective. Use 'other' for non-family relationships and specify relationship_label."
                },
                "relationship_label": {
                    "type": "string",
                    "description": "Label for non-family relationships when relationship_type='other' (e.g., 'manager', 'direct report', 'mentor', 'colleague', 'team member', 'client', 'vendor'). This provides structured categorization separate from the notes field. Optional but recommended for work relationships."
                },
                "notes": {
                    "type": "string",
                    "description": "Additional context about the relationship (optional)"
                },
                "bidirectional": {
                    "type": "boolean",
                    "description": "If true, automatically creates the reverse relationship (e.g., parent->child creates child->parent). Default: true",
                    "default": True
                }
            },
            "required": ["person_id", "related_person_id", "relationship_type"]
        }
    )


def _update_person_tool() -> types.Tool:
    return types.Tool(
        name="update_person",
        description="Update existing person fields. Only updates provided fields, leaves others unchanged. Use this to modify biographical information like birthday, ethnicity, origin_location, known_since, last_interaction_date, or to change relationship/category classifications. Can also link to Google Contacts via google_people_id.",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the person to update"
                },
                "canonical_name": {
                    "type": "string",
                    "description": "Primary name (optional - only if changing name)"
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of nicknames/alternate names (optional - replaces existing)"
                },
                "relationship": {
                    "type": "string",
                    "enum": ["friend", "family", "colleague", "partner", "acquaintance", "mentor", "mentee", "other"],
                    "description": "Type of relationship (optional)"
                },
                "category": {
                    "type": "string",
                    "enum": ["close_friend", "friend", "acquaintance", "family", "work", "not_met", "other"],
                    "description": "Closeness/organizational category (optional)"
                },
                "kinship_to_owner": {
                    "type": "string",
                    "description": "Specific kinship relation to the owner (e.g., 'mother', 'father', 'brother', 'sister', 'son', 'daughter') (optional)"
                },
                "birthday": {
                    "type": "string",
                    "description": "Birthday as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional). Must match one of these formats."
                },
                "death_date": {
                    "type": "string",
                    "description": "Date of death as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional). Must match one of these formats."
                },
                "ethnicity": {
                    "type": "string",
                    "description": "Ethnicity/cultural background (optional)"
                },
                "origin_location": {
                    "type": "string",
                    "description": "Place of origin (optional)"
                },
                "known_since": {
                    "type": "string",
                    "description": "Year or date first met (optional). Must be partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD."
                },
                "last_interaction_date": {
                    "type": "string",
                    "description": "Most recent interaction as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)."
                },
                "google_people_id": {
                    "type": "string",
                    "description": "Google People API resource ID for this contact (e.g., 'people/c1234567890'). Links to Google Contacts for contact info and social profiles (optional)."
                }
            },
            "required": ["person_id"]
        }
    )


def _add_person_work_tool() -> types.Tool:
    return types.Tool(
        name="add_person_work",
        description="Add work history for a person with temporal_location support. Creates a temporal_location entry representing the time period at a workplace, then links it to the person's work history. Supports data reuse for colleagues at same company/location/time.",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the person"
                },
                "company": {
                    "type": "string",
                    "description": "Company name (required)"
                },
                "role": {
                    "type": "string",
                    "description": "Job title/role (required)"
                },
                "location_id": {
                    "type": "string",
                    "description": "UUID of workplace location from locations table (required - Design #31)"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)."
                },
                "end_date": {
                    "type": "string",
                    "description": "End date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional - omit if current)."
                },
                "is_current": {
                    "type": "boolean",
                    "description": "Whether this is current employment (default: false)",
                    "default": False
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes about the work history (optional)"
                }
            },
            "required": ["person_id", "company", "role", "location_id"]
        }
    )


def _add_person_education_tool() -> types.Tool:
    return types.Tool(
        name="add_person_education",
        description="Add education history for a person with temporal_location support. Creates a temporal_location entry representing the time period at an educational institution, then links it to the person's education history. Supports data reuse for classmates at same school/time.",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the person"
                },
                "institution": {
                    "type": "string",
                    "description": "Educational institution name (required)"
                },
                "degree": {
                    "type": "string",
                    "description": "Degree type (e.g., 'BS', 'MS', 'PhD', 'High School Diploma') (required)"
                },
                "field": {
                    "type": "string",
                    "description": "Field of study (e.g., 'Computer Science', 'Biology') (optional)"
                },
                "location_id": {
                    "type": "string",
                    "description": "UUID of institution location from locations table (required - Design #31)"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)."
                },
                "end_date": {
                    "type": "string",
                    "description": "End date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional - omit if current)."
                },
                "is_current": {
                    "type": "boolean",
                    "description": "Whether this is current education (default: false)",
                    "default": False
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes about the education history (optional)"
                }
            },
            "required": ["person_id", "institution", "degree", "location_id"]
        }
    )


def _add_person_residence_tool() -> types.Tool:
    return types.Tool(
        name="add_person_residence",
        description="Add residence history for a person with temporal_location support. Creates a temporal_location entry representing the time period at a residence, then links it to the person's residential history. Supports data reuse for roommates at same location/time. Use temporal_location_id to reuse an existing temporal_location (e.g., for roommates/flatmates who shared the same place during the same time period).",
        inputSchema={
            "type": "object",
            "properties": {
                "person_id": {
                    "type": "string",
                    "description": "UUID of the person"
                },
                "location_id": {
                    "type": "string",
                    "description": "UUID of residence location from locations table. Required unless temporal_location_id is provided."
                },
                "temporal_location_id": {
                    "type": "string",
                    "description": "UUID of an existing temporal_location to reuse (optional). Use this when adding residence for roommates/flatmates who shared the same location during the same time period. If provided, location_id/start_date/end_date/is_current are ignored."
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional). Ignored if temporal_location_id is provided."
                },
                "end_date": {
                    "type": "string",
                    "description": "End date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional - omit if current). Ignored if temporal_location_id is provided."
                },
                "is_current": {
                    "type": "boolean",
                    "description": "Whether this is current residence (default: false). Ignored if temporal_location_id is provided.",
                    "default": False
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes about the residence (optional)"
                }
            },
            "required": ["person_id"]
        }
    )


def _update_person_relationship_tool() -> types.Tool:
    return types.Tool(
        name="update_person_relationship",
        description="Update an existing relationship's label or notes. Useful for updating the relationship_label on auto-generated reciprocal relationships (e.g., after creating 'manager' relationship, update the reverse to have 'direct report' label). Only updates provided fields, leaves others unchanged.",
        inputSchema={
            "type": "object",
            "properties": {
                "relationship_id": {
                    "type": "string",
                    "description": "UUID of the relationship to update (from execute_sql_query on person_relationships table)"
                },
                "relationship_label": {
                    "type": "string",
                    "description": "Updated label for the relationship (e.g., 'manager', 'direct report', 'mentor', 'colleague'). Optional."
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes about the relationship. Optional."
                }
            },
            "required": ["relationship_id"]
        }
    )

def _update_person_work_tool() -> types.Tool:
    return types.Tool(
        name="update_person_work",
        description="Update existing work history entry. Use this to add missing dates, correct company names or roles, update location, or modify notes. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "work_id": {
                    "type": "string",
                    "description": "UUID of the work history entry to update (from get_person_details)"
                },
                "company": {
                    "type": "string",
                    "description": "Updated company name (optional)"
                },
                "role": {
                    "type": "string",
                    "description": "Updated job title/role (optional)"
                },
                "location_id": {
                    "type": "string",
                    "description": "Updated workplace location UUID (optional)"
                },
                "start_date": {
                    "type": "string",
                    "description": "Updated start date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)"
                },
                "end_date": {
                    "type": "string",
                    "description": "Updated end date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional - omit if current)"
                },
                "is_current": {
                    "type": "boolean",
                    "description": "Whether this is current employment (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                }
            },
            "required": ["work_id"]
        }
    )


def _update_person_education_tool() -> types.Tool:
    return types.Tool(
        name="update_person_education",
        description="Update existing education history entry. Use this to add missing dates, correct institution names or degrees, update field of study, or modify notes. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "education_id": {
                    "type": "string",
                    "description": "UUID of the education history entry to update (from get_person_details)"
                },
                "institution": {
                    "type": "string",
                    "description": "Updated institution name (optional)"
                },
                "degree": {
                    "type": "string",
                    "description": "Updated degree type (optional)"
                },
                "field": {
                    "type": "string",
                    "description": "Updated field of study (optional)"
                },
                "location_id": {
                    "type": "string",
                    "description": "Updated institution location UUID (optional)"
                },
                "start_date": {
                    "type": "string",
                    "description": "Updated start date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)"
                },
                "end_date": {
                    "type": "string",
                    "description": "Updated end date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional - omit if current)"
                },
                "is_current": {
                    "type": "boolean",
                    "description": "Whether this is current education (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                }
            },
            "required": ["education_id"]
        }
    )


def _update_person_residence_tool() -> types.Tool:
    return types.Tool(
        name="update_person_residence",
        description="Update existing residence history entry. Use this to add missing dates, correct location, or modify notes. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "residence_id": {
                    "type": "string",
                    "description": "UUID of the residence history entry to update (from get_person_details)"
                },
                "location_id": {
                    "type": "string",
                    "description": "Updated residence location UUID (optional)"
                },
                "start_date": {
                    "type": "string",
                    "description": "Updated start date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional)"
                },
                "end_date": {
                    "type": "string",
                    "description": "Updated end date as partial ISO-8601 string: YYYY, YYYY-MM, or YYYY-MM-DD (optional - omit if current)"
                },
                "is_current": {
                    "type": "boolean",
                    "description": "Whether this is current residence (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                }
            },
            "required": ["residence_id"]
        }
    )


def _update_person_note_tool() -> types.Tool:
    return types.Tool(
        name="update_person_note",
        description="Update existing biographical note about a person. Use this to correct text, change categorization, update tags, or modify context. Only provided fields will be updated.",
        inputSchema={
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "UUID of the note to update (from get_person_details)"
                },
                "text": {
                    "type": "string",
                    "description": "Updated note text (optional)"
                },
                "note_type": {
                    "type": "string",
                    "enum": ["biographical", "health", "preference", "interest", "story", "personality", "achievement", "other"],
                    "description": "Updated note type (optional)"
                },
                "category": {
                    "type": "string",
                    "enum": ["health", "personality", "hobbies", "family", "career", "preferences", "beliefs", "achievements", "stories", "other"],
                    "description": "Updated category (optional)"
                },
                "note_date": {
                    "type": "string",
                    "description": "Updated date in YYYY-MM-DD format (optional)"
                },
                "source": {
                    "type": "string",
                    "enum": ["conversation", "observation", "social_media", "told_by_others", "inference", "document", "other"],
                    "description": "Updated source (optional)"
                },
                "context": {
                    "type": "string",
                    "description": "Updated context (optional)"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Updated tags (optional, replaces existing)"
                }
            },
            "required": ["note_id"]
        }
    )


def _merge_duplicate_people_tool() -> types.Tool:
    return types.Tool(
        name="merge_duplicate_people",
        description="""Merge a duplicate person record into the canonical person. Atomically reassigns all event participations and relationships from the duplicate to the canonical person, then soft-deletes the duplicate.

USE CASES:
- Merging duplicate people created from voice transcription errors
- Consolidating records when the same person was created twice

EXAMPLE:
{
  "canonical_person_id": "uuid-of-person-to-keep",
  "duplicate_person_id": "uuid-of-duplicate-to-merge",
  "dry_run": true
}

dry_run=true returns a preview of affected records without making changes.
After confirming the preview, call again with dry_run=false to execute the merge.

NOTE: Person notes, work history, education, and residences on the duplicate are NOT reassigned — they remain linked to the (now soft-deleted) duplicate for audit trail purposes.""",
        inputSchema={
            "type": "object",
            "properties": {
                "canonical_person_id": {
                    "type": "string",
                    "description": "UUID of the person to keep (the canonical record)"
                },
                "duplicate_person_id": {
                    "type": "string",
                    "description": "UUID of the duplicate person to merge and delete"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, returns a preview of changes without executing. Default: false",
                    "default": False
                }
            },
            "required": ["canonical_person_id", "duplicate_person_id"]
        }
    )

