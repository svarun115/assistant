"""
People Management Handlers
Domain-specific handlers for people, relationships, and biographical information.
"""

import json
import logging
from datetime import datetime
from typing import Any, List
from uuid import UUID
from mcp import types

logger = logging.getLogger(__name__)


def _normalize_known_since(value):
    """Normalize known_since to a partial ISO-8601 date string (YYYY, YYYY-MM, or YYYY-MM-DD).
    Accepts an int (year), a YYYY-MM-DD string, a YYYY string, or date/datetime objects.
    Returns string date or None if value is falsy.
    """
    if value is None:
        return None
    
    # Handle date/datetime objects by converting to ISO string
    if hasattr(value, 'isoformat'):
        iso_str = value.isoformat()
        # Strip time component if present
        return iso_str.split('T')[0]
    
    # If it's an int, convert to YYYY string
    if isinstance(value, int):
        if 1000 <= value <= 9999:
            return str(value)
        return None
    # If it's a string, validate and return
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        # Strip time component if present
        v = v.split('T')[0]
        # Try ISO date first - validate by attempting to parse
        try:
            datetime.fromisoformat(v)
            return v  # Valid ISO format, return as-is
        except Exception:
            pass
        # Try YYYY partial string
        try:
            year = int(v)
            if 1000 <= year <= 9999:
                return str(year)
        except Exception:
            pass
    # Unknown format => return None
    return None


def _validate_partial_date_string(value) -> str:
    """Validate incoming partial date strings (YYYY, YYYY-MM, YYYY-MM-DD).
    Returns the original string if valid, otherwise raises ValueError.
    Handles date objects by converting them to ISO format strings.
    """
    if value is None:
        return None
    
    # Handle date/datetime objects by converting to ISO string
    if hasattr(value, 'isoformat'):
        value = value.isoformat()
    
    # Ensure it's a string
    if not isinstance(value, str):
        value = str(value)
    
    v = value.strip()
    if not v:
        return None
    
    # Strip time component if present (e.g., from datetime)
    v = v.split('T')[0]
    
    import re
    if re.fullmatch(r"\d{4}", v) or re.fullmatch(r"\d{4}-\d{2}", v) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    raise ValueError(f"Invalid date format '{value}'. Expected YYYY, YYYY-MM, or YYYY-MM-DD.")


async def handle_create_person(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle create_person tool - create person with biographical details"""
    try:
        # Accept birthday as partial date string
        birthday = None
        if arguments.get("birthday"):
            birthday = _validate_partial_date_string(arguments["birthday"])
        
        # Accept death_date as partial date string
        death_date = None
        if arguments.get("death_date"):
            death_date = _validate_partial_date_string(arguments["death_date"])
        
        # Parse last_interaction_date as partial date string
        last_interaction_date = None
        if arguments.get("last_interaction_date"):
            last_interaction_date = _validate_partial_date_string(arguments["last_interaction_date"])
        
        # Create person via repository
        person = await repos.people.create_person_full(
            canonical_name=arguments["canonical_name"],
            aliases=arguments.get("aliases", []),
            relationship=arguments.get("relationship"),
            category=arguments.get("category"),
            kinship_to_owner=arguments.get("kinship_to_owner"),
            birthday=birthday,
            death_date=death_date,
            ethnicity=arguments.get("ethnicity"),
            origin_location=arguments.get("origin_location"),
            known_since=_normalize_known_since(arguments.get("known_since")),
            last_interaction_date=last_interaction_date,
            google_people_id=arguments.get("google_people_id")
        )
        
        result = {
            "person_id": str(person.id),
            "canonical_name": person.canonical_name,
            "relationship": person.relationship,
            "category": person.category,
            "birthday": person.birthday if person.birthday else None,
            "known_since": person.known_since,
            "google_people_id": person.google_people_id if hasattr(person, 'google_people_id') else None,
            "message": "✅ Person created successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2, default=str)
        )]
        
    except Exception as e:
        logger.error(f"Error creating person: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error creating person: {str(e)}"}, indent=2)
        )]


async def handle_add_person_note(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle add_person_note tool - add biographical note"""
    try:
        person_id = UUID(arguments['person_id'])
        
        # note_date is stored as VARCHAR(10) in the database (ISO-8601 partial date string)
        # Ensure it's always a string, converting from date objects if needed
        note_date = arguments.get('note_date')
        if note_date is not None:
            # Handle case where a date object is passed instead of string
            if hasattr(note_date, 'isoformat'):
                note_date = note_date.isoformat()
            elif not isinstance(note_date, str):
                note_date = str(note_date)
            
            # Validate it's a valid date format
            try:
                datetime.fromisoformat(note_date.split('T')[0])  # Handle datetime strings too
            except (ValueError, AttributeError):
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Invalid note_date format: {note_date}. Use YYYY, YYYY-MM, or YYYY-MM-DD"}, indent=2)
                )]
        
        # Ensure tags is a list
        tags = arguments.get('tags', [])
        if tags is None:
            tags = []
        elif not isinstance(tags, list):
            tags = [tags] if tags else []
        
        # Add note via repository
        note = await repos.people.add_note(
            person_id=person_id,
            text=str(arguments['text']),  # Ensure text is string
            note_type=str(arguments['note_type']) if arguments.get('note_type') else None,
            category=str(arguments['category']) if arguments.get('category') else None,
            note_date=note_date,
            source=str(arguments['source']) if arguments.get('source') else None,
            context=str(arguments['context']) if arguments.get('context') else None,
            tags=tags
        )
        
        response = {
            "note_id": str(note['id']),
            "person_id": str(note['person_id']),
            "text": note['text'],
            "note_type": note.get('note_type'),
            "category": note.get('category'),
            "tags": note.get('tags', []),
            "message": "✅ Person note added successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error adding person note: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error adding person note: {str(e)}"}, indent=2)
        )]


async def handle_add_person_relationship(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle add_person_relationship tool - define relationship between people"""
    try:
        person_id = UUID(arguments['person_id'])
        related_person_id = UUID(arguments['related_person_id'])
        
        # Add relationship via repository
        result = await repos.people.add_relationship(
            person_id=person_id,
            related_person_id=related_person_id,
            relationship_type=arguments['relationship_type'],
            relationship_label=arguments.get('relationship_label'),
            notes=arguments.get('notes'),
            bidirectional=arguments.get('bidirectional', True)
        )
        
        response = {
            "relationship_id": str(result['id']),
            "person_id": str(result['person_id']),
            "related_person_id": str(result['related_person_id']),
            "relationship_type": result['relationship_type'],
            "bidirectional": arguments.get('bidirectional', True)
        }
        
        if 'reverse_type' in result:
            response['reverse_relationship_type'] = result['reverse_type']
            response['message'] = f"✅ Created bidirectional relationship: {result['relationship_type']} ↔ {result['reverse_type']}"
        else:
            response['message'] = "✅ Relationship added successfully"
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error adding relationship: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error adding relationship: {str(e)}"}, indent=2)
        )]


async def handle_update_person(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle update_person tool - update existing person fields"""
    try:
        person_id = UUID(arguments['person_id'])
        
        # Parse optional date fields as partial date strings
        birthday = None
        if 'birthday' in arguments and arguments['birthday']:
            birthday = _validate_partial_date_string(arguments['birthday'])
        
        death_date = None
        if 'death_date' in arguments and arguments['death_date']:
            death_date = _validate_partial_date_string(arguments['death_date'])
        
        last_interaction_date = None
        if 'last_interaction_date' in arguments and arguments['last_interaction_date']:
            last_interaction_date = _validate_partial_date_string(arguments['last_interaction_date'])
        
        # Update person with only provided fields
        result = await repos.people.update_person(
            person_id=person_id,
            canonical_name=arguments.get('canonical_name'),
            aliases=arguments.get('aliases'),
            relationship=arguments.get('relationship'),
            category=arguments.get('category'),
            kinship_to_owner=arguments.get('kinship_to_owner'),
            birthday=birthday,
            death_date=death_date,
            ethnicity=arguments.get('ethnicity'),
            origin_location=arguments.get('origin_location'),
            known_since=_normalize_known_since(arguments.get('known_since')),
            last_interaction_date=last_interaction_date,
            google_people_id=arguments.get('google_people_id')
        )
        
        response = {
            "person_id": str(result['id']),
            "canonical_name": result['canonical_name'],
            "updated_fields": {k: v for k, v in arguments.items() if k != 'person_id' and v is not None},
            "message": "✅ Person updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error updating person: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating person: {str(e)}"}, indent=2)
        )]


async def handle_delete_person(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle delete_person tool - soft delete (mark as deleted, preserve data)"""
    try:
        person_id = UUID(arguments['person_id'])
        
        # Get person before deletion to show what was deleted
        person = await repos.people.get_by_id(person_id)
        if not person:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Person not found: {person_id}"}, indent=2)
            )]
        
        # Soft delete the person
        result = await repos.people.delete_person(person_id)
        
        response = {
            "deleted_person_id": str(result['id']),
            "canonical_name": result['canonical_name'],
            "is_deleted": result['is_deleted'],
            "deleted_at": str(result['deleted_at']),
            "note": "Soft delete: data preserved for audit trail. Use undelete_person to restore if accidentally deleted.",
            "message": "✅ Person marked as deleted (soft delete)"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error deleting person: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting person: {str(e)}"}, indent=2)
        )]


async def handle_update_person_relationship(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle update_person_relationship tool - update relationship label/notes"""
    try:
        relationship_id = UUID(arguments['relationship_id'])
        relationship_label = arguments.get('relationship_label')
        notes = arguments.get('notes')
        
        result = await repos.people.update_relationship(
            relationship_id=relationship_id,
            relationship_label=relationship_label,
            notes=notes
        )
        
        response = {
            "relationship_id": str(result['id']),
            "person_id": str(result['person_id']),
            "related_person_id": str(result['related_person_id']),
            "relationship_type": result['relationship_type'],
            "relationship_label": result.get('relationship_label'),
            "notes": result.get('notes'),
            "message": "✅ Relationship updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error updating relationship: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating relationship: {str(e)}"}, indent=2)
        )]


async def handle_delete_person_relationship(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle delete_person_relationship tool - delete incorrect relationships"""
    try:
        relationship_id = UUID(arguments['relationship_id'])
        
        # Delete the relationship (reciprocal deleted automatically by trigger)
        result = await repos.people.delete_relationship(relationship_id)
        
        response = {
            "deleted_relationship_id": str(result['id']),
            "person_id": str(result['person_id']),
            "related_person_id": str(result['related_person_id']),
            "relationship_type": result['relationship_type'],
            "note": "Reciprocal relationship automatically deleted by database trigger",
            "message": "✅ Relationship(s) deleted successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except ValueError as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error deleting relationship: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting relationship: {str(e)}"}, indent=2)
        )]



async def handle_undelete_person(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle undelete_person tool - restore a deleted person"""
    try:
        person_id = UUID(arguments['person_id'])
        
        # Restore the person
        result = await repos.people.undelete_person(person_id)
        
        response = {
            "restored_person_id": str(result['id']),
            "canonical_name": result['canonical_name'],
            "is_deleted": result['is_deleted'],
            "deleted_at": result.get('deleted_at'),
            "note": "Person successfully restored to active status. Now visible in searches and queries.",
            "message": "✅ Person restored to active status"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error undeleting person: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring person: {str(e)}"}, indent=2)
        )]
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting person: {str(e)}"}, indent=2)
        )]


async def handle_add_person_work(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle add_person_work tool - add work history with temporal_location"""
    try:
        person_id = UUID(arguments['person_id'])
        location_value = arguments.get('location_id')
        if not location_value:
            raise ValueError("location_id is required for add_person_work (Design #31)")
        location_id = UUID(location_value)
        
        # Parse date fields
        start_date = None
        if arguments.get('start_date'):
            start_date = _validate_partial_date_string(arguments['start_date'])
        
        end_date = None
        if arguments.get('end_date'):
            end_date = _validate_partial_date_string(arguments['end_date'])
        
        result = await repos.people.add_work(
            person_id=person_id,
            company=arguments['company'],
            role=arguments['role'],
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            is_current=arguments.get('is_current', False),
            notes=arguments.get('notes')
        )
        
        response = {
            "work_id": str(result['id']),
            "person_id": str(result['person_id']),
            "temporal_location_id": result['temporal_location_id'],
            "company": result['company'],
            "role": result['role'],
            "message": "✅ Work history added successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error adding work history: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error adding work history: {str(e)}"}, indent=2)
        )]


async def handle_add_person_education(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle add_person_education tool - add education history with temporal_location"""
    try:
        person_id = UUID(arguments['person_id'])
        location_value = arguments.get('location_id')
        if not location_value:
            raise ValueError("location_id is required for add_person_education (Design #31)")
        location_id = UUID(location_value)
        
        # Parse date fields
        start_date = None
        if arguments.get('start_date'):
            start_date = _validate_partial_date_string(arguments['start_date'])
        
        end_date = None
        if arguments.get('end_date'):
            end_date = _validate_partial_date_string(arguments['end_date'])
        
        result = await repos.people.add_education(
            person_id=person_id,
            institution=arguments['institution'],
            degree=arguments['degree'],
            location_id=location_id,
            field=arguments.get('field'),
            start_date=start_date,
            end_date=end_date,
            is_current=arguments.get('is_current', False),
            notes=arguments.get('notes')
        )
        
        response = {
            "education_id": str(result['id']),
            "person_id": str(result['person_id']),
            "temporal_location_id": result['temporal_location_id'],
            "institution": result['institution'],
            "degree": result['degree'],
            "field": result.get('field'),
            "message": "✅ Education history added successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error adding education history: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error adding education history: {str(e)}"}, indent=2)
        )]


async def handle_add_person_residence(arguments: dict, repos: Any) -> List[types.TextContent]:
    """Handle add_person_residence tool - add residence history with temporal_location"""
    try:
        person_id = UUID(arguments['person_id'])
        
        # Check if temporal_location_id is provided (for reusing existing temporal_location)
        temporal_location_id = arguments.get('temporal_location_id')
        
        if temporal_location_id:
            # Reuse existing temporal_location (Issue #107 fix)
            result = await repos.people.add_residence_with_temporal_location(
                person_id=person_id,
                temporal_location_id=UUID(temporal_location_id),
                notes=arguments.get('notes')
            )
            response = {
                "residence_id": str(result['id']),
                "person_id": str(result['person_id']),
                "temporal_location_id": result['temporal_location_id'],
                "message": "✅ Residence history added successfully (reused existing temporal_location)"
            }
        else:
            # Create new temporal_location (original behavior)
            location_value = arguments.get('location_id')
            if not location_value:
                raise ValueError("location_id is required for add_person_residence unless temporal_location_id is provided")
            location_id = UUID(location_value)
            
            # Parse date fields
            start_date = None
            if arguments.get('start_date'):
                start_date = _validate_partial_date_string(arguments['start_date'])
            
            end_date = None
            if arguments.get('end_date'):
                end_date = _validate_partial_date_string(arguments['end_date'])
            
            result = await repos.people.add_residence(
                person_id=person_id,
                location_id=location_id,
                start_date=start_date,
                end_date=end_date,
                is_current=arguments.get('is_current', False),
                notes=arguments.get('notes')
            )
            response = {
                "residence_id": str(result['id']),
                "person_id": str(result['person_id']),
                "temporal_location_id": result['temporal_location_id'],
                "message": "✅ Residence history added successfully"
            }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error adding residence history: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error adding residence history: {str(e)}"}, indent=2)
        )]


async def handle_update_person_work(db: Any, repos: Any, arguments: dict) -> List[types.TextContent]:
    """Handle update_person_work tool - update work history entry"""
    try:
        work_id = UUID(arguments['work_id'])
        
        # Build update fields dictionary - only include fields that were provided
        update_fields = {}
        
        if 'company' in arguments:
            update_fields['company'] = arguments['company']
        
        if 'role' in arguments:
            update_fields['role'] = arguments['role']
        
        if 'notes' in arguments:
            update_fields['notes'] = arguments['notes']
        
        # Handle temporal_location fields (dates, location)
        temporal_location_updates = {}
        
        if 'start_date' in arguments and arguments['start_date']:
            temporal_location_updates['start_date'] = _validate_partial_date_string(arguments['start_date'])
        
        if 'end_date' in arguments:
            if arguments['end_date']:
                temporal_location_updates['end_date'] = _validate_partial_date_string(arguments['end_date'])
            else:
                temporal_location_updates['end_date'] = None
        
        if 'is_current' in arguments:
            temporal_location_updates['is_current'] = arguments['is_current']
        
        if 'location_id' in arguments:
            temporal_location_updates['location_id'] = UUID(arguments['location_id'])
        
        # Update person_work table
        async with db.pool.acquire() as conn:
            # First, get the current temporal_location_id
            work_record = await conn.fetchrow(
                "SELECT temporal_location_id, person_id FROM person_work WHERE id = $1",
                work_id
            )
            
            if not work_record:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Work history entry not found: {work_id}"}, indent=2)
                )]
            
            temporal_location_id = work_record['temporal_location_id']
            person_id = work_record['person_id']
            
            # Update person_work fields if any
            if update_fields:
                set_clauses = []
                values = []
                param_num = 1
                
                for field, value in update_fields.items():
                    set_clauses.append(f"{field} = ${param_num}")
                    values.append(value)
                    param_num += 1
                
                set_clauses.append(f"updated_at = ${param_num}")
                values.append(datetime.now())
                param_num += 1
                
                query = f"UPDATE person_work SET {', '.join(set_clauses)} WHERE id = ${param_num} RETURNING *"
                values.append(work_id)
                
                await conn.execute(query, *values)
            
            # Update temporal_location if needed
            if temporal_location_updates:
                set_clauses = []
                values = []
                param_num = 1
                
                for field, value in temporal_location_updates.items():
                    set_clauses.append(f"{field} = ${param_num}")
                    values.append(value)
                    param_num += 1
                
                query = f"UPDATE temporal_locations SET {', '.join(set_clauses)} WHERE id = ${param_num}"
                values.append(temporal_location_id)
                
                await conn.execute(query, *values)
            
            # Get updated work record with location details
            result = await conn.fetchrow("""
                SELECT pw.id, pw.person_id, pw.company, pw.role, pw.notes,
                       tl.start_date, tl.end_date, tl.is_current,
                       l.canonical_name as location_name
                FROM person_work pw
                JOIN temporal_locations tl ON pw.temporal_location_id = tl.id
                LEFT JOIN locations l ON tl.location_id = l.id
                WHERE pw.id = $1
            """, work_id)
        
        response = {
            "work_id": str(result['id']),
            "person_id": str(result['person_id']),
            "company": result['company'],
            "role": result['role'],
            "location": result.get('location_name'),
            "start_date": result.get('start_date'),
            "end_date": result.get('end_date'),
            "is_current": result.get('is_current'),
            "notes": result.get('notes'),
            "updated_fields": list(update_fields.keys()) + list(temporal_location_updates.keys()),
            "message": "✅ Work history updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error updating work history: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating work history: {str(e)}"}, indent=2)
        )]


async def handle_update_person_education(db: Any, repos: Any, arguments: dict) -> List[types.TextContent]:
    """Handle update_person_education tool - update education history entry"""
    try:
        education_id = UUID(arguments['education_id'])
        
        # Build update fields dictionary
        update_fields = {}
        
        if 'institution' in arguments:
            update_fields['institution'] = arguments['institution']
        
        if 'degree' in arguments:
            update_fields['degree'] = arguments['degree']
        
        if 'field' in arguments:
            update_fields['field'] = arguments['field']
        
        if 'notes' in arguments:
            update_fields['notes'] = arguments['notes']
        
        # Handle temporal_location fields
        temporal_location_updates = {}
        
        if 'start_date' in arguments and arguments['start_date']:
            temporal_location_updates['start_date'] = _validate_partial_date_string(arguments['start_date'])
        
        if 'end_date' in arguments:
            if arguments['end_date']:
                temporal_location_updates['end_date'] = _validate_partial_date_string(arguments['end_date'])
            else:
                temporal_location_updates['end_date'] = None
        
        if 'is_current' in arguments:
            temporal_location_updates['is_current'] = arguments['is_current']
        
        if 'location_id' in arguments:
            temporal_location_updates['location_id'] = UUID(arguments['location_id'])
        
        async with db.pool.acquire() as conn:
            # Get temporal_location_id
            edu_record = await conn.fetchrow(
                "SELECT temporal_location_id, person_id FROM person_education WHERE id = $1",
                education_id
            )
            
            if not edu_record:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Education history entry not found: {education_id}"}, indent=2)
                )]
            
            temporal_location_id = edu_record['temporal_location_id']
            
            # Update person_education fields
            if update_fields:
                set_clauses = []
                values = []
                param_num = 1
                
                for field, value in update_fields.items():
                    set_clauses.append(f"{field} = ${param_num}")
                    values.append(value)
                    param_num += 1
                
                set_clauses.append(f"updated_at = ${param_num}")
                values.append(datetime.now())
                param_num += 1
                
                query = f"UPDATE person_education SET {', '.join(set_clauses)} WHERE id = ${param_num}"
                values.append(education_id)
                
                await conn.execute(query, *values)
            
            # Update temporal_location
            if temporal_location_updates:
                set_clauses = []
                values = []
                param_num = 1
                
                for field, value in temporal_location_updates.items():
                    set_clauses.append(f"{field} = ${param_num}")
                    values.append(value)
                    param_num += 1
                
                query = f"UPDATE temporal_locations SET {', '.join(set_clauses)} WHERE id = ${param_num}"
                values.append(temporal_location_id)
                
                await conn.execute(query, *values)
            
            # Get updated record
            result = await conn.fetchrow("""
                SELECT pe.id, pe.person_id, pe.institution, pe.degree, pe.field, pe.notes,
                       tl.start_date, tl.end_date, tl.is_current,
                       l.canonical_name as location_name
                FROM person_education pe
                JOIN temporal_locations tl ON pe.temporal_location_id = tl.id
                LEFT JOIN locations l ON tl.location_id = l.id
                WHERE pe.id = $1
            """, education_id)
        
        response = {
            "education_id": str(result['id']),
            "person_id": str(result['person_id']),
            "institution": result['institution'],
            "degree": result['degree'],
            "field": result.get('field'),
            "location": result.get('location_name'),
            "start_date": result.get('start_date'),
            "end_date": result.get('end_date'),
            "is_current": result.get('is_current'),
            "notes": result.get('notes'),
            "updated_fields": list(update_fields.keys()) + list(temporal_location_updates.keys()),
            "message": "✅ Education history updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error updating education history: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating education history: {str(e)}"}, indent=2)
        )]


async def handle_update_person_residence(db: Any, repos: Any, arguments: dict) -> List[types.TextContent]:
    """Handle update_person_residence tool - update residence history entry"""
    try:
        residence_id = UUID(arguments['residence_id'])
        
        # Build update fields dictionary
        update_fields = {}
        
        if 'notes' in arguments:
            update_fields['notes'] = arguments['notes']
        
        # Handle temporal_location fields
        temporal_location_updates = {}
        
        if 'start_date' in arguments and arguments['start_date']:
            temporal_location_updates['start_date'] = _validate_partial_date_string(arguments['start_date'])
        
        if 'end_date' in arguments:
            if arguments['end_date']:
                temporal_location_updates['end_date'] = _validate_partial_date_string(arguments['end_date'])
            else:
                temporal_location_updates['end_date'] = None
        
        if 'is_current' in arguments:
            temporal_location_updates['is_current'] = arguments['is_current']
        
        if 'location_id' in arguments:
            temporal_location_updates['location_id'] = UUID(arguments['location_id'])
        
        async with db.pool.acquire() as conn:
            # Get temporal_location_id (exclude soft-deleted records)
            res_record = await conn.fetchrow(
                "SELECT temporal_location_id, person_id FROM person_residences WHERE id = $1 AND is_deleted = FALSE",
                residence_id
            )
            
            if not res_record:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Residence history entry not found or deleted: {residence_id}"}, indent=2)
                )]
            
            temporal_location_id = res_record['temporal_location_id']
            
            # Update person_residences fields
            if update_fields:
                set_clauses = []
                values = []
                param_num = 1
                
                for field, value in update_fields.items():
                    set_clauses.append(f"{field} = ${param_num}")
                    values.append(value)
                    param_num += 1
                
                set_clauses.append(f"updated_at = ${param_num}")
                values.append(datetime.now())
                param_num += 1
                
                query = f"UPDATE person_residences SET {', '.join(set_clauses)} WHERE id = ${param_num}"
                values.append(residence_id)
                
                await conn.execute(query, *values)
            
            # Update temporal_location
            if temporal_location_updates:
                set_clauses = []
                values = []
                param_num = 1
                
                for field, value in temporal_location_updates.items():
                    set_clauses.append(f"{field} = ${param_num}")
                    values.append(value)
                    param_num += 1
                
                query = f"UPDATE temporal_locations SET {', '.join(set_clauses)} WHERE id = ${param_num}"
                values.append(temporal_location_id)
                
                await conn.execute(query, *values)
            
            # Get updated record
            result = await conn.fetchrow("""
                SELECT pr.id, pr.person_id, pr.notes,
                       tl.start_date, tl.end_date, tl.is_current,
                       l.canonical_name as location_name
                FROM person_residences pr
                JOIN temporal_locations tl ON pr.temporal_location_id = tl.id
                LEFT JOIN locations l ON tl.location_id = l.id
                WHERE pr.id = $1
            """, residence_id)
        
        response = {
            "residence_id": str(result['id']),
            "person_id": str(result['person_id']),
            "location": result.get('location_name'),
            "start_date": result.get('start_date'),
            "end_date": result.get('end_date'),
            "is_current": result.get('is_current'),
            "notes": result.get('notes'),
            "updated_fields": list(update_fields.keys()) + list(temporal_location_updates.keys()),
            "message": "✅ Residence history updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error updating residence history: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating residence history: {str(e)}"}, indent=2)
        )]


async def handle_update_person_note(arguments: dict, db: Any) -> List[types.TextContent]:
    """Handle update_person_note tool - update biographical note"""
    try:
        note_id = UUID(arguments['note_id'])
        
        # Build update fields dictionary
        update_fields = {}
        
        if 'text' in arguments:
            update_fields['text'] = arguments['text']
        
        if 'note_type' in arguments:
            update_fields['note_type'] = arguments['note_type']
        
        if 'category' in arguments:
            update_fields['category'] = arguments['category']
        
        if 'note_date' in arguments:
            if arguments['note_date']:
                update_fields['note_date'] = _validate_partial_date_string(arguments['note_date'])
            else:
                update_fields['note_date'] = None
        
        if 'source' in arguments:
            update_fields['source'] = arguments['source']
        
        if 'context' in arguments:
            update_fields['context'] = arguments['context']
        
        if 'tags' in arguments:
            update_fields['tags'] = arguments['tags']
        
        if not update_fields:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "No fields provided to update"}, indent=2)
            )]
        
        async with db.pool.acquire() as conn:
            # Check if note exists
            note_check = await conn.fetchrow(
                "SELECT person_id FROM person_notes WHERE id = $1",
                note_id
            )
            
            if not note_check:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Person note not found: {note_id}"}, indent=2)
                )]
            
            # Update note
            set_clauses = []
            values = []
            param_num = 1
            
            for field, value in update_fields.items():
                set_clauses.append(f"{field} = ${param_num}")
                values.append(value)
                param_num += 1
            
            set_clauses.append(f"updated_at = ${param_num}")
            values.append(datetime.now())
            param_num += 1
            
            query = f"UPDATE person_notes SET {', '.join(set_clauses)} WHERE id = ${param_num} RETURNING *"
            values.append(note_id)
            
            result = await conn.fetchrow(query, *values)
        
        response = {
            "note_id": str(result['id']),
            "person_id": str(result['person_id']),
            "text": result.get('text'),
            "note_type": result.get('note_type'),
            "category": result.get('category'),
            "note_date": result.get('note_date'),
            "source": result.get('source'),
            "context": result.get('context'),
            "tags": result.get('tags', []),
            "updated_fields": list(update_fields.keys()),
            "message": "✅ Person note updated successfully"
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(response, indent=2, default=str)
        )]
    
    except Exception as e:
        logger.error(f"Error updating person note: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating person note: {str(e)}"}, indent=2)
        )]


async def handle_delete_person_residence(db: Any, arguments: dict) -> List[types.TextContent]:
    """Soft delete a person residence record"""
    try:
        residence_id = arguments.get("residence_id")
        if not residence_id:
            raise ValueError("residence_id is required")
        
        async with db.pool.acquire() as conn:
            query = """
                UPDATE person_residences
                SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id, person_id, temporal_location_id
            """
            
            result = await conn.fetchrow(query, UUID(residence_id))
            if not result:
                raise ValueError(f"Residence record {residence_id} not found or already deleted")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "residence_id": str(result['id']),
                    "person_id": str(result['person_id']),
                    "temporal_location_id": str(result['temporal_location_id']),
                    "message": "✅ Person residence deleted (soft delete - can be restored)"
                }, indent=2)
            )]
    
    except Exception as e:
        logger.error(f"Error deleting person residence: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting person residence: {str(e)}"}, indent=2)
        )]


async def handle_undelete_person_residence(db: Any, arguments: dict) -> List[types.TextContent]:
    """Restore a soft-deleted person residence record"""
    try:
        residence_id = arguments.get("residence_id")
        if not residence_id:
            raise ValueError("residence_id is required")
        
        async with db.pool.acquire() as conn:
            query = """
                UPDATE person_residences
                SET is_deleted = FALSE, deleted_at = NULL
                WHERE id = $1 AND is_deleted = TRUE
                RETURNING id, person_id, temporal_location_id
            """
            
            result = await conn.fetchrow(query, UUID(residence_id))
            if not result:
                raise ValueError(f"Residence record {residence_id} not found or not deleted")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "residence_id": str(result['id']),
                    "person_id": str(result['person_id']),
                    "temporal_location_id": str(result['temporal_location_id']),
                    "message": "✅ Person residence restored successfully"
                }, indent=2)
            )]
    
    except Exception as e:
        logger.error(f"Error restoring person residence: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error restoring person residence: {str(e)}"}, indent=2)
        )]


async def handle_merge_duplicate_people(db, repos, arguments: dict) -> list[types.TextContent]:
    """Merge a duplicate person into the canonical person. Reassigns event participations
    and relationships, then soft-deletes the duplicate."""
    try:
        canonical_id = UUID(arguments["canonical_person_id"])
        duplicate_id = UUID(arguments["duplicate_person_id"])
        dry_run = arguments.get("dry_run", False)

        # Validate: no self-merge
        if canonical_id == duplicate_id:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "canonical_person_id and duplicate_person_id cannot be the same"}, indent=2)
            )]

        # Validate both exist and aren't deleted
        canonical = await repos.people.get_by_id(canonical_id)
        if not canonical:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Canonical person not found: {canonical_id}"}, indent=2)
            )]
        if getattr(canonical, 'is_deleted', False):
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Canonical person is deleted: {canonical_id}"}, indent=2)
            )]

        duplicate = await repos.people.get_by_id(duplicate_id)
        if not duplicate:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Duplicate person not found: {duplicate_id}"}, indent=2)
            )]
        if getattr(duplicate, 'is_deleted', False):
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Duplicate person is already deleted: {duplicate_id}"}, indent=2)
            )]

        async with db.pool.acquire() as conn:
            # Count affected event_participants
            ep_count = await conn.fetchval(
                "SELECT COUNT(*) FROM event_participants WHERE person_id = $1",
                duplicate_id
            )
            # Count conflicts (both people on same event)
            ep_conflicts = await conn.fetchval(
                """SELECT COUNT(*) FROM event_participants ep1
                   JOIN event_participants ep2 ON ep1.event_id = ep2.event_id
                   WHERE ep1.person_id = $1 AND ep2.person_id = $2""",
                duplicate_id, canonical_id
            )
            # Count affected relationships
            rel_count = await conn.fetchval(
                """SELECT COUNT(*) FROM person_relationships
                   WHERE person_id = $1 OR related_person_id = $1""",
                duplicate_id
            )

            if dry_run:
                result = {
                    "dry_run": True,
                    "canonical_person": {"id": str(canonical_id), "name": canonical.canonical_name},
                    "duplicate_person": {"id": str(duplicate_id), "name": duplicate.canonical_name},
                    "event_participations_to_reassign": ep_count,
                    "event_conflicts_to_remove": ep_conflicts,
                    "relationships_to_reassign": rel_count,
                    "message": f"Preview: {ep_count} event participation(s) will be reassigned "
                               f"({ep_conflicts} conflict(s) removed), {rel_count} relationship(s) "
                               f"will be reassigned, duplicate will be soft-deleted."
                }
                return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

            # Execute merge in a transaction
            async with conn.transaction():
                # 1. Delete conflicting event_participants (both people on same event)
                conflicts_deleted = await conn.execute(
                    """DELETE FROM event_participants
                       WHERE person_id = $1
                       AND event_id IN (
                           SELECT event_id FROM event_participants WHERE person_id = $2
                       )""",
                    duplicate_id, canonical_id
                )

                # 2. Reassign remaining event_participants
                ep_updated = await conn.execute(
                    "UPDATE event_participants SET person_id = $2 WHERE person_id = $1",
                    duplicate_id, canonical_id
                )

                # 3. Delete conflicting relationships (would create duplicate after reassignment)
                await conn.execute(
                    """DELETE FROM person_relationships
                       WHERE person_id = $1
                       AND related_person_id IN (
                           SELECT related_person_id FROM person_relationships WHERE person_id = $2
                       )""",
                    duplicate_id, canonical_id
                )
                await conn.execute(
                    """DELETE FROM person_relationships
                       WHERE related_person_id = $1
                       AND person_id IN (
                           SELECT person_id FROM person_relationships WHERE related_person_id = $2
                       )""",
                    duplicate_id, canonical_id
                )

                # 4. Reassign remaining relationships
                await conn.execute(
                    "UPDATE person_relationships SET person_id = $2 WHERE person_id = $1",
                    duplicate_id, canonical_id
                )
                await conn.execute(
                    "UPDATE person_relationships SET related_person_id = $2 WHERE related_person_id = $1",
                    duplicate_id, canonical_id
                )

                # 5. Soft-delete the duplicate
                await conn.execute(
                    "UPDATE people SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW() WHERE id = $1",
                    duplicate_id
                )

            # Parse affected counts from command tags
            ep_updated_count = int(ep_updated.split()[-1]) if ep_updated else 0
            conflicts_deleted_count = int(conflicts_deleted.split()[-1]) if conflicts_deleted else 0

            result = {
                "dry_run": False,
                "canonical_person": {"id": str(canonical_id), "name": canonical.canonical_name},
                "duplicate_person": {"id": str(duplicate_id), "name": duplicate.canonical_name},
                "events_reassigned": ep_updated_count,
                "conflicts_removed": conflicts_deleted_count,
                "relationships_reassigned": rel_count,
                "duplicate_deleted": True,
                "message": f"✅ Merged '{duplicate.canonical_name}' into '{canonical.canonical_name}'. "
                           f"{ep_updated_count} event participation(s) reassigned, "
                           f"{conflicts_deleted_count} conflict(s) removed, "
                           f"duplicate soft-deleted."
            }
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except ValueError as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Invalid UUID format: {str(e)}"}, indent=2)
        )]
    except Exception as e:
        logger.error(f"Error merging duplicate people: {str(e)}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error merging duplicate people: {str(e)}"}, indent=2)
        )]
