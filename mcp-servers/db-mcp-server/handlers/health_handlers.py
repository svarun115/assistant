"""
Health Tracking Handlers
Handles: log_health_condition, log_medicine, log_supplement, 
         get_recent_conditions, get_recent_medicines, get_recent_supplements
"""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4
from mcp import types


def _validate_partial_date_string(value: str):
    """Validate incoming partial date strings (YYYY, YYYY-MM, YYYY-MM-DD).
    Returns the original string if valid, otherwise raises ValueError.
    """
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    import re
    if re.fullmatch(r"\d{4}", v) or re.fullmatch(r"\d{4}-\d{2}", v) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    raise ValueError(f"Invalid date format '{value}'. Expected YYYY, YYYY-MM, or YYYY-MM-DD.")


async def handle_log_health_condition(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Log a health condition (illness or injury) as an event"""
    try:
        from models import EventCreate, HealthConditionCreate, EventType
        from uuid import UUID

        condition_type = arguments.get("condition_type")
        condition_name = arguments.get("condition_name")
        severity = arguments.get("severity")
        severity_score = arguments.get("severity_score")
        is_sport_related = arguments.get("is_sport_related", False)
        sport_type = arguments.get("sport_type")
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        notes = arguments.get("notes")
        person_id_str = arguments.get("person_id")  # NEW: Optional person parameter

        # Convert person_id string to UUID if provided
        person_id = UUID(person_id_str) if person_id_str else None
        
        # Validate partial date strings
        start_date = _validate_partial_date_string(start_date)
        end_date = _validate_partial_date_string(end_date)
        
        # Parse start/end times for the event (use full date if provided)
        start_time = None
        end_time = None
        if start_date and len(start_date) == 10:
            start_time = datetime.fromisoformat(f"{start_date}T00:00:00")
        if end_date and len(end_date) == 10:
            end_time = datetime.fromisoformat(f"{end_date}T23:59:59")
        
        # If no valid start_time, use current time
        if start_time is None:
            start_time = datetime.now()
        
        # Create associated event using proper model
        event = EventCreate(
            event_type=EventType.GENERIC,
            title=f"{condition_type.title()}: {condition_name}",
            start_time=start_time,
            end_time=end_time,
            category="health",
            description=notes or f"Health {condition_type} tracking"
        )
        
        # Create the health condition using proper model
        # Note: event_id will be set by create_with_event, we use a placeholder UUID
        condition = HealthConditionCreate(
            event_id=UUID('00000000-0000-0000-0000-000000000000'),  # Placeholder, will be replaced
            person_id=person_id,  # NEW: Pass person_id
            condition_type=condition_type,
            condition_name=condition_name,
            severity=severity,
            severity_score=severity_score,
            is_sport_related=is_sport_related,
            sport_type=sport_type,
            start_date=start_date,
            end_date=end_date,
            notes=notes
        )

        async with db.pool.acquire() as conn:
            # Use create_with_event which properly handles both event and condition creation
            # Pass person_id to create_with_event
            result_obj = await repos.health_conditions.create_with_event(
                event, condition, person_id=person_id
            )
            
            result = {
                "status": "success",
                "condition_id": str(result_obj.condition.id),
                "event_id": str(result_obj.event.id),
                "person_id": str(result_obj.condition.person_id) if result_obj.condition.person_id else None,  # NEW
                "condition_type": condition_type,
                "condition_name": condition_name,
                "severity": severity,
                "date_range": f"{start_date}" + (f" to {end_date}" if end_date else " (ongoing)"),
                "message": "✅ Health condition logged"
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error logging health condition: {str(e)}"}, indent=2)
        )]


async def handle_log_medicine(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Log medicine taken"""
    try:
        from models import HealthMedicineCreate
        from uuid import UUID
        
        medicine_name = arguments.get("medicine_name")
        dosage = arguments.get("dosage")
        dosage_unit = arguments.get("dosage_unit")
        frequency = arguments.get("frequency")
        condition_id = arguments.get("condition_id")
        event_id = arguments.get("event_id")
        log_date = arguments.get("log_date")
        log_time = arguments.get("log_time")
        taken_at = arguments.get("taken_at")
        notes = arguments.get("notes")
        
        # Handle taken_at timestamp format (convenience parameter)
        if taken_at and not log_date:
            if isinstance(taken_at, str):
                # Parse ISO timestamp: "2025-11-16T14:30:00"
                parts = taken_at.split('T')
                log_date = parts[0]
                if len(parts) > 1:
                    log_time = parts[1]
        
        # Validate partial date string for log_date
        log_date = _validate_partial_date_string(log_date)

        # Create medicine log entry using Pydantic model
        medicine = HealthMedicineCreate(
            medicine_name=medicine_name,
            dosage=dosage,
            dosage_unit=dosage_unit,
            frequency=frequency,
            condition_id=UUID(condition_id) if condition_id else None,
            event_id=UUID(event_id) if event_id else None,
            log_date=log_date,
            log_time=log_time,
            notes=notes
        )
        
        async with db.pool.acquire() as conn:
            result_dict = await repos.health_medicines.create(medicine)
            medicine_id = result_dict["id"]
            
            result = {
                "status": "success",
                "medicine_id": str(medicine_id),
                "medicine_name": medicine_name,
                "dosage": dosage,
                "dosage_unit": dosage_unit,
                "frequency": frequency,
                "logged_at": f"{log_date}T{log_time}",
                "message": "✅ Medicine logged"
            }
            
            if condition_id:
                result["linked_to_condition"] = str(condition_id)
            if event_id:
                result["linked_to_event"] = str(event_id)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error logging medicine: {str(e)}"}, indent=2)
        )]


async def handle_log_supplement(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Log dietary supplement taken"""
    try:
        from models import HealthSupplementCreate
        from uuid import UUID
        
        supplement_name = arguments.get("supplement_name")
        amount = arguments.get("amount")
        amount_unit = arguments.get("amount_unit")
        frequency = arguments.get("frequency")
        event_id = arguments.get("event_id")
        log_date = arguments.get("log_date")
        log_time = arguments.get("log_time")
        taken_at = arguments.get("taken_at")
        notes = arguments.get("notes")
        
        # Handle taken_at timestamp format (convenience parameter)
        if taken_at and not log_date:
            if isinstance(taken_at, str):
                # Parse ISO timestamp: "2025-11-16T14:30:00"
                parts = taken_at.split('T')
                log_date = parts[0]
                if len(parts) > 1:
                    log_time = parts[1]
        
        # Create supplement log entry using Pydantic model
        supplement = HealthSupplementCreate(
            supplement_name=supplement_name,
            amount=amount,
            amount_unit=amount_unit,
            frequency=frequency,
            event_id=UUID(event_id) if event_id else None,
            log_date=_validate_partial_date_string(log_date),
            log_time=log_time,
            notes=notes
        )
        
        async with db.pool.acquire() as conn:
            result_dict = await repos.health_supplements.create(supplement)
            supplement_id = result_dict["id"]
            
            result = {
                "status": "success",
                "supplement_id": str(supplement_id),
                "supplement_name": supplement_name,
                "amount": amount,
                "amount_unit": amount_unit,
                "frequency": frequency,
                "logged_at": f"{log_date}T{log_time}",
                "message": "✅ Supplement logged"
            }
            
            if event_id:
                result["linked_to_event"] = str(event_id)
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error logging supplement: {str(e)}"}, indent=2)
        )]


async def handle_update_health_condition(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update existing health condition"""
    try:
        from uuid import UUID
        from datetime import date

        condition_id = arguments.get("condition_id")
        if not condition_id:
            raise ValueError("condition_id is required")

        # Build update fields
        updates = {}
        if "condition_name" in arguments:
            updates["condition_name"] = arguments["condition_name"]
        if "severity" in arguments:
            updates["severity"] = arguments["severity"]
        if "severity_score" in arguments:
            updates["severity_score"] = arguments["severity_score"]
        if "end_date" in arguments:
            # Validate and convert to date object
            validated_date = _validate_partial_date_string(arguments["end_date"])
            if validated_date and len(validated_date) == 10:  # Full date YYYY-MM-DD
                updates["end_date"] = date.fromisoformat(validated_date)
            else:
                updates["end_date"] = validated_date  # Partial date, keep as string
        if "notes" in arguments:
            updates["notes"] = arguments["notes"]
        
        if not updates:
            raise ValueError("No fields to update")
        
        async with db.pool.acquire() as conn:
            # Build SET clause
            set_parts = [f"{k} = ${i+2}" for i, k in enumerate(updates.keys())]
            set_clause = ", ".join(set_parts)
            values = [UUID(condition_id)] + list(updates.values())
            
            query = f"""
                UPDATE health_conditions
                SET {set_clause}
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id
            """
            
            result = await conn.fetchrow(query, *values)
            if not result:
                raise ValueError(f"Health condition {condition_id} not found")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "condition_id": str(condition_id),
                    "updated_fields": list(updates.keys()),
                    "message": "✅ Health condition updated"
                }, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating health condition: {str(e)}"}, indent=2)
        )]


async def handle_update_medicine(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update existing medicine log entry"""
    try:
        from uuid import UUID
        
        medicine_id = arguments.get("medicine_id")
        if not medicine_id:
            raise ValueError("medicine_id is required")
        
        # Build update fields
        updates = {}
        if "medicine_name" in arguments:
            updates["medicine_name"] = arguments["medicine_name"]
        if "dosage" in arguments:
            updates["dosage"] = arguments["dosage"]
        if "dosage_unit" in arguments:
            updates["dosage_unit"] = arguments["dosage_unit"]
        if "frequency" in arguments:
            updates["frequency"] = arguments["frequency"]
        if "log_date" in arguments:
            updates["log_date"] = _validate_partial_date_string(arguments["log_date"])
        if "log_time" in arguments:
            updates["log_time"] = arguments["log_time"]
        if "notes" in arguments:
            updates["notes"] = arguments["notes"]
        
        if not updates:
            raise ValueError("No fields to update")
        
        async with db.pool.acquire() as conn:
            # Build SET clause
            set_parts = [f"{k} = ${i+2}" for i, k in enumerate(updates.keys())]
            set_clause = ", ".join(set_parts)
            values = [UUID(medicine_id)] + list(updates.values())
            
            query = f"""
                UPDATE health_medicines
                SET {set_clause}
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id
            """
            
            result = await conn.fetchrow(query, *values)
            if not result:
                raise ValueError(f"Medicine log {medicine_id} not found")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "medicine_id": str(medicine_id),
                    "updated_fields": list(updates.keys()),
                    "message": "✅ Medicine log updated"
                }, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating medicine: {str(e)}"}, indent=2)
        )]


async def handle_update_supplement(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update existing supplement log entry"""
    try:
        from uuid import UUID
        
        supplement_id = arguments.get("supplement_id")
        if not supplement_id:
            raise ValueError("supplement_id is required")
        
        # Build update fields
        updates = {}
        if "supplement_name" in arguments:
            updates["supplement_name"] = arguments["supplement_name"]
        if "amount" in arguments:
            updates["amount"] = arguments["amount"]
        if "amount_unit" in arguments:
            updates["amount_unit"] = arguments["amount_unit"]
        if "frequency" in arguments:
            updates["frequency"] = arguments["frequency"]
        if "log_date" in arguments:
            updates["log_date"] = _validate_partial_date_string(arguments["log_date"])
        if "log_time" in arguments:
            updates["log_time"] = arguments["log_time"]
        if "notes" in arguments:
            updates["notes"] = arguments["notes"]
        
        if not updates:
            raise ValueError("No fields to update")
        
        async with db.pool.acquire() as conn:
            # Build SET clause
            set_parts = [f"{k} = ${i+2}" for i, k in enumerate(updates.keys())]
            set_clause = ", ".join(set_parts)
            values = [UUID(supplement_id)] + list(updates.values())
            
            query = f"""
                UPDATE health_supplements
                SET {set_clause}
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id
            """
            
            result = await conn.fetchrow(query, *values)
            if not result:
                raise ValueError(f"Supplement log {supplement_id} not found")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "supplement_id": str(supplement_id),
                    "updated_fields": list(updates.keys()),
                    "message": "✅ Supplement log updated"
                }, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating supplement: {str(e)}"}, indent=2)
        )]


async def handle_delete_health_condition(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete a health condition"""
    try:
        from uuid import UUID
        
        condition_id = arguments.get("condition_id")
        if not condition_id:
            raise ValueError("condition_id is required")
        
        async with db.pool.acquire() as conn:
            query = """
                UPDATE health_conditions
                SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id
            """
            
            result = await conn.fetchrow(query, UUID(condition_id))
            if not result:
                raise ValueError(f"Health condition {condition_id} not found or already deleted")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "condition_id": str(condition_id),
                    "message": "✅ Health condition deleted"
                }, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting health condition: {str(e)}"}, indent=2)
        )]


async def handle_delete_medicine(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete a medicine log"""
    try:
        from uuid import UUID
        
        medicine_id = arguments.get("medicine_id")
        if not medicine_id:
            raise ValueError("medicine_id is required")
        
        async with db.pool.acquire() as conn:
            query = """
                UPDATE health_medicines
                SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id
            """
            
            result = await conn.fetchrow(query, UUID(medicine_id))
            if not result:
                raise ValueError(f"Medicine log {medicine_id} not found or already deleted")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "medicine_id": str(medicine_id),
                    "message": "✅ Medicine log deleted"
                }, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting medicine: {str(e)}"}, indent=2)
        )]


async def handle_delete_supplement(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete a supplement log"""
    try:
        from uuid import UUID
        
        supplement_id = arguments.get("supplement_id")
        if not supplement_id:
            raise ValueError("supplement_id is required")
        
        async with db.pool.acquire() as conn:
            query = """
                UPDATE health_supplements
                SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND is_deleted = FALSE
                RETURNING id
            """
            
            result = await conn.fetchrow(query, UUID(supplement_id))
            if not result:
                raise ValueError(f"Supplement log {supplement_id} not found or already deleted")
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "supplement_id": str(supplement_id),
                    "message": "✅ Supplement log deleted"
                }, indent=2)
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting supplement: {str(e)}"}, indent=2)
        )]


# =============================================================================
# Health Condition Progression Logs
# =============================================================================

async def handle_log_health_condition_update(db, repos, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Log a progression update for an existing health condition."""
    try:
        from uuid import UUID
        from models import HealthConditionLogCreate, HealthConditionSeverity

        condition_id = UUID(arguments["condition_id"])
        log_date = arguments["log_date"]

        # Validate condition exists
        condition = await repos.health_conditions.get_by_id(condition_id)
        if not condition:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Health condition not found: {condition_id}"}, indent=2)
            )]

        severity = None
        if arguments.get("severity"):
            severity = HealthConditionSeverity(arguments["severity"])

        log_create = HealthConditionLogCreate(
            condition_id=condition_id,
            log_date=log_date,
            severity=severity,
            severity_score=arguments.get("severity_score"),
            notes=arguments.get("notes")
        )

        result = await repos.health_condition_logs.create(log_create)

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "success",
                "log_id": str(result["id"]),
                "condition_id": str(condition_id),
                "condition_name": condition.get("condition_name", ""),
                "log_date": log_date,
                "severity": arguments.get("severity"),
                "severity_score": arguments.get("severity_score"),
                "message": f"✅ Logged progression update for {condition.get('condition_name', 'condition')} on {log_date}"
            }, indent=2, default=str)
        )]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error logging condition update: {str(e)}"}, indent=2)
        )]


async def handle_update_health_condition_log(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Update an existing health condition progression log entry."""
    try:
        from uuid import UUID

        log_id = UUID(arguments["log_id"])

        # Build dynamic update
        updates = []
        params = [log_id]
        param_idx = 2

        for field in ["severity", "severity_score", "notes"]:
            if field in arguments and arguments[field] is not None:
                updates.append(f"{field} = ${param_idx}")
                params.append(arguments[field])
                param_idx += 1

        if "log_date" in arguments and arguments["log_date"] is not None:
            updates.append(f"log_date = ${param_idx}")
            params.append(datetime.strptime(arguments["log_date"], '%Y-%m-%d').date())
            param_idx += 1

        if not updates:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": "No fields to update"}, indent=2)
            )]

        query = f"""
            UPDATE health_condition_logs
            SET {', '.join(updates)}
            WHERE id = $1 AND is_deleted = FALSE
            RETURNING *
        """

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        if not row:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Health condition log not found: {log_id}"}, indent=2)
            )]

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "success",
                "log_id": str(log_id),
                "updated_fields": [u.split(" = ")[0] for u in updates],
                "message": "✅ Health condition log updated"
            }, indent=2)
        )]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error updating condition log: {str(e)}"}, indent=2)
        )]


async def handle_delete_health_condition_log(db, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Soft delete a health condition progression log entry."""
    try:
        from uuid import UUID

        log_id = UUID(arguments["log_id"])

        query = """
            UPDATE health_condition_logs
            SET is_deleted = TRUE, deleted_at = NOW()
            WHERE id = $1 AND is_deleted = FALSE
            RETURNING id
        """

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, log_id)

        if not row:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Health condition log not found or already deleted: {log_id}"}, indent=2)
            )]

        return [types.TextContent(
            type="text",
            text=json.dumps({
                "status": "success",
                "log_id": str(log_id),
                "message": "✅ Health condition log deleted"
            }, indent=2)
        )]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Error deleting condition log: {str(e)}"}, indent=2)
        )]


