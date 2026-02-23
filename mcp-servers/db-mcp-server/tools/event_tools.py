"""
Event Query MCP Tools
Specialized tools for searching events, finding activities, and exploring hierarchical structures.
"""

from mcp import types


def _create_event_tool() -> types.Tool:
    """Create an event - supports all types (generic, sleep, reflection, work)."""
    return types.Tool(
        name="create_event",
        description="""Create an event of any type: generic, sleep, reflection, or work.

EVENT TYPES & FIELDS:

1. SLEEP (event_type="sleep")
   - Tracks: quality, interruptions, dream_recall
   - Auto-calculates duration from start/end times
   - Default category: "health"
   
2. REFLECTION (event_type="reflection")
   - Tracks: mood, mood_score, key_insights, action_items, prompt_question
   - Creates reflection metadata automatically
   - Default category: "personal"
   
3. WORK (event_type="work")
   - Tracks: work_type, work_context, productivity
   - Handles participants (meetings)
   - Default category: "work"
   
4. GENERIC (event_type="generic" - default)
   - Standard event with no special handling

HYBRID RESOLUTION:
- location_id: Uses existing location (validates existence)
- participant_ids: Uses existing people (validates existence)

EXAMPLE - SLEEP:
{
  "event_type": "sleep",
  "start_time": "2025-11-04T23:00:00",
  "end_time": "2025-11-05T07:30:00",
    "location_id": "<location-uuid>",
  "quality": "good",
  "interruptions": 1,
  "dream_recall": true
}

EXAMPLE - REFLECTION:
{
  "event_type": "reflection",
  "title": "Daily Reflection",
  "start_time": "2025-11-04T21:00:00",
  "mood": "thoughtful",
  "mood_score": 7,
  "key_insights": ["Made good progress on project", "Need better work-life balance"],
  "action_items": ["Schedule personal time", "Review project timeline"]
}

EXAMPLE - WORK:
{
  "event_type": "work",
  "title": "Team standup + backend work",
  "start_time": "2025-11-04T09:00:00",
  "end_time": "2025-11-04T12:00:00",
  "work_type": "meeting",
  "work_context": "company_work",
  "productivity": "high_productivity",
  "participant_ids": ["<person-uuid-1>", "<person-uuid-2>"],
    "location_id": "<location-uuid>"
}

EXAMPLE - GENERIC:
{
  "event_type": "generic",
  "title": "Coffee with friend",
  "start_time": "2025-11-04T15:00:00",
  "end_time": "2025-11-04T16:00:00",
    "location_id": "<location-uuid>",
  "participant_ids": ["<person-uuid>"]
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "Type of event: 'sleep', 'reflection', 'work', or 'generic' (default)",
                    "enum": ["sleep", "reflection", "work", "generic"],
                    "default": "generic"
                },
                "title": {
                    "type": "string",
                    "description": "Event title (optional - auto-generated for sleep based on duration)"
                },
                "description": {
                    "type": "string",
                    "description": "Event description (optional)"
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time (ISO 8601 format: YYYY-MM-DDTHH:MM:SS) [REQUIRED]"
                },
                "end_time": {
                    "type": "string",
                    "description": "End time (ISO 8601 format, optional)"
                },
                "category": {
                    "type": "string",
                    "enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
                    "description": "Event category. Auto-set based on event_type if not provided (sleep->health, reflection->personal, work->work)"
                },
                "significance": {
                    "type": "string",
                    "description": "Significance: 'routine', 'notable', 'major_milestone'",
                    "enum": ["routine", "notable", "major_milestone"],
                    "default": "routine"
                },
                "location_id": {
                    "type": "string",
                    "description": "Location UUID (if known from previous search)"
                },
                "parent_event_id": {
                    "type": "string",
                    "description": "Parent event UUID for hierarchical events (e.g., trip contains daily activities). Creates event hierarchy without affecting time ranges."
                },
                "participant_ids": {
                    "type": "array",
                    "description": "List of participant UUIDs",
                    "items": {"type": "string"}
                },
                "interaction_mode": {
                    "type": "string",
                    "description": "Mode of interaction for participants (e.g., 'in_person', 'virtual_video', 'virtual_audio', 'text_async')",
                    "enum": ["in_person", "virtual_video", "virtual_audio", "text_async", "other"]
                },
                "tags": {
                    "type": "array",
                    "description": "Tags for categorization",
                    "items": {"type": "string"}
                },
                
                # Sleep-specific fields
                "quality": {
                    "type": "string",
                    "description": "[SLEEP] Sleep quality: 'poor', 'fair', 'good', 'excellent'",
                    "enum": ["poor", "fair", "good", "excellent"]
                },
                "interruptions": {
                    "type": "integer",
                    "description": "[SLEEP] Number of times woken up (optional)"
                },
                "dream_recall": {
                    "type": "boolean",
                    "description": "[SLEEP] Whether you remember dreaming (optional)"
                },
                
                # Reflection-specific fields
                "mood": {
                    "type": "string",
                    "description": "[REFLECTION] Mood during reflection (e.g., 'thoughtful', 'anxious', 'happy')"
                },
                "mood_score": {
                    "type": "integer",
                    "description": "[REFLECTION] Mood rating 1-10"
                },
                "prompt_question": {
                    "type": "string",
                    "description": "[REFLECTION] Reflection prompt or question"
                },
                "key_insights": {
                    "type": "array",
                    "description": "[REFLECTION] Key insights from reflection",
                    "items": {"type": "string"}
                },
                "action_items": {
                    "type": "array",
                    "description": "[REFLECTION] Action items from reflection",
                    "items": {"type": "string"}
                },
                "reflection_type": {
                    "type": "string",
                    "description": "[REFLECTION] Type of reflection (optional)"
                },
                
                # Work-specific fields
                "work_type": {
                    "type": "string",
                    "description": "[WORK] Type of work: 'focused_work', 'meeting', 'admin', 'creative', 'planning'",
                    "enum": ["focused_work", "meeting", "admin", "creative", "planning"]
                },
                "work_context": {
                    "type": "string",
                    "description": "[WORK] Context: 'company_work', 'personal_project', 'freelance', 'learning'",
                    "enum": ["company_work", "personal_project", "freelance", "learning"]
                },
                "productivity": {
                    "type": "string",
                    "description": "[WORK] Productivity level: 'high_productivity', 'medium_productivity', 'low_productivity'",
                    "enum": ["high_productivity", "medium_productivity", "low_productivity"]
                },
                "additional_tags": {
                    "type": "array",
                    "description": "[WORK] Additional tags beyond work_type/context/productivity",
                    "items": {"type": "string"}
                },
                
                # Generic notes
                "notes": {
                    "type": "string",
                    "description": "Additional notes (optional)"
                },
                
                # Secondhand event tracking
                "source_person_id": {
                    "type": "string",
                    "description": "UUID of the person who provided this information (for secondhand events). Use with parent_event_id to fully track: parent_event_id = WHERE you learned it (conversation), source_person_id = WHO told you."
                }
            },
            "required": ["start_time"]
        }
    )


def _update_event_tool() -> types.Tool:
    return types.Tool(
        name="update_event",
        description="""Update an existing event of any type (sleep, reflection, work, generic).

Type-specific field updates supported:
- SLEEP: quality, interruptions, dream_recall
- REFLECTION: mood, mood_score, key_insights, action_items, prompt_question
- WORK: work_type, work_context, productivity, participant updates
- GENERIC: standard event fields

EXAMPLE - SLEEP UPDATE:
{
  "event_id": "uuid-of-sleep-event",
  "event_type": "sleep",
  "quality": "excellent",
  "interruptions": 0
}

EXAMPLE - REFLECTION UPDATE:
{
  "event_id": "uuid-of-reflection",
  "event_type": "reflection",
  "mood": "accomplished",
  "mood_score": 8,
  "key_insights": ["Made real progress", "Need to focus on details"]
}

EXAMPLE - WORK UPDATE:
{
  "event_id": "uuid-of-work-block",
  "event_type": "work",
  "productivity": "high_productivity",
  "work_type": "focused_work"
}
""",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "UUID of the event to update (required)"
                },
                "event_type": {
                    "type": "string",
                    "description": "Event type (optional - detected from current event if not provided)",
                    "enum": ["sleep", "reflection", "work", "generic"]
                },
                "title": {
                    "type": "string",
                    "description": "Updated title (optional)"
                },
                "description": {
                    "type": "string",
                    "description": "Updated description (optional)"
                },
                "start_time": {
                    "type": "string",
                    "description": "Updated start time (ISO 8601, optional)"
                },
                "end_time": {
                    "type": "string",
                    "description": "Updated end time (ISO 8601, optional)"
                },
                "location_id": {
                    "type": "string",
                    "description": "Updated location UUID (optional)"
                },
                "parent_event_id": {
                    "type": "string",
                    "description": "Updated parent event UUID (optional, use null to remove parent)"
                },
                "external_event_id": {
                    "type": "string",
                    "description": "Link to external system ID (e.g., Garmin activity ID). Use with external_event_source."
                },
                "external_event_source": {
                    "type": "string",
                    "description": "Source system for external_event_id (e.g., 'garmin', 'apple_health', 'fitbit', 'strava')"
                },
                "category": {
                    "type": "string",
                    "enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
                    "description": "Updated event category"
                },
                "significance": {
                    "type": "string",
                    "enum": ["routine", "notable", "major_milestone"],
                    "description": "Updated significance (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Updated notes (optional)"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Updated tags (optional)"
                },
                "participant_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "[WORK] Updated participant UUIDs"
                },
                "interaction_mode": {
                    "type": "string",
                    "description": "Updated mode of interaction for participants (e.g., 'in_person', 'virtual_video', 'virtual_audio', 'text_async')",
                    "enum": ["in_person", "virtual_video", "virtual_audio", "text_async", "other"]
                },
                
                # Sleep-specific fields
                "quality": {
                    "type": "string",
                    "description": "[SLEEP] Updated sleep quality",
                    "enum": ["poor", "fair", "good", "excellent"]
                },
                "interruptions": {
                    "type": "integer",
                    "description": "[SLEEP] Updated number of interruptions"
                },
                "dream_recall": {
                    "type": "boolean",
                    "description": "[SLEEP] Updated dream recall status"
                },
                
                # Reflection-specific fields
                "mood": {
                    "type": "string",
                    "description": "[REFLECTION] Updated mood"
                },
                "mood_score": {
                    "type": "integer",
                    "description": "[REFLECTION] Updated mood score (1-10)"
                },
                "prompt_question": {
                    "type": "string",
                    "description": "[REFLECTION] Updated prompt question"
                },
                "key_insights": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "[REFLECTION] Updated key insights"
                },
                "action_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "[REFLECTION] Updated action items"
                },
                "reflection_type": {
                    "type": "string",
                    "description": "[REFLECTION] Updated reflection type"
                },
                
                # Work-specific fields
                "work_type": {
                    "type": "string",
                    "description": "[WORK] Updated work type",
                    "enum": ["focused_work", "meeting", "admin", "creative", "planning"]
                },
                "work_context": {
                    "type": "string",
                    "description": "[WORK] Updated work context",
                    "enum": ["company_work", "personal_project", "freelance", "learning"]
                },
                "productivity": {
                    "type": "string",
                    "description": "[WORK] Updated productivity level",
                    "enum": ["high_productivity", "medium_productivity", "low_productivity"]
                },
                
                # Secondhand event tracking
                "source_person_id": {
                    "type": "string",
                    "description": "UUID of the person who provided this information (for secondhand events). Use with parent_event_id to fully track: parent_event_id = WHERE you learned it (conversation), source_person_id = WHO told you."
                }
            },
            "required": ["event_id"]
        }
    )


def get_event_tools() -> list[types.Tool]:
    """
    Returns only creation/write tools for events.

    Tools included:
    - create_event: Create a generic event
    - update_event: Update event metadata

    Delete/restore: use delete_entity / restore_entity with entity_type="event".
    For searching/querying events, use execute_sql_query instead (SQL-first architecture).
    """
    return [
        _create_event_tool(),
        _update_event_tool(),
    ]
