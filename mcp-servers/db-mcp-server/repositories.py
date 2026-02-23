"""
Repository layer for database operations
Provides CRUD operations for all entities
"""

from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union
from uuid import UUID
from datetime import date, datetime

from database import DatabaseConnection
from models import (
    Person, PersonCreate,
    Location, LocationCreate,
    Exercise, ExerciseCreate,
    Workout, WorkoutCreate, WorkoutExercise, ExerciseSet,
    Meal, MealCreate, MealItem,
    WorkDay, WorkDayCreate, WorkBlock,
    SleepSession, SleepSessionCreate,
    Event, EventCreate, EventParticipant,
    Reflection, ReflectionCreate,
    JournalDay, JournalDayCreate,
    # Journal entry models
    JournalEntry, JournalEntryCreate,
)

if TYPE_CHECKING:
    # Import additional model types only for type checking to avoid runtime import cycles
    from models import (
        WorkoutWithEvent, MealWithEvent, MealItemCreate,
        CommuteCreate, CommuteWithEvent,
        EntertainmentCreate, EntertainmentWithEvent,
        HealthConditionCreate, HealthConditionWithEvent,
        HealthMedicineCreate, HealthSupplementCreate,
    )


class BaseRepository:
    """Base repository with common operations"""
    
    def __init__(self, db: DatabaseConnection):
        self.db = db
    
    async def _dict_to_model(self, data: Dict[str, Any], model_class):
        """Convert database record to Pydantic model"""
        if data is None:
            return None
        # Convert NULL arrays to empty lists for Pydantic
        data_dict = dict(data)
        # Convert date fields to ISO string if model expects str
        if hasattr(model_class, '__annotations__'):
            for key, value in data_dict.items():
                field_type = model_class.__annotations__.get(key, None)
                if value is None:
                    if field_type and 'List' in str(field_type):
                        data_dict[key] = []
                # Convert date to str for fields like journal_date
                if field_type == str and isinstance(value, date):
                    data_dict[key] = value.isoformat()
        return model_class(**data_dict)
    
    async def _list_to_models(self, data_list: List[Dict[str, Any]], model_class):
        """Convert list of database records to Pydantic models"""
        return [model_class(**dict(row)) for row in data_list]
    
    async def _add_deletion_filter(self, query: str, include_deleted: bool = False) -> str:
        """Add deletion filter to query if needed"""
        if not include_deleted and "WHERE" in query:
            # Add to existing WHERE clause
            return query.replace("WHERE", "WHERE is_deleted = FALSE AND")
        elif not include_deleted:
            # Add new WHERE clause (assumes query doesn't have WHERE)
            return query + " WHERE is_deleted = FALSE"
        return query


class PeopleRepository(BaseRepository):
    """Repository for people operations"""
    
    async def _find_or_create_temporal_location(
        self,
        location_id: UUID,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        is_current: bool = False,
        notes: Optional[str] = None
    ) -> UUID:
        """
        Find existing temporal_location or create new one.
        
        Reuses existing temporal_location if found with matching:
        - location_id
        - start_date (NULL-safe comparison)
        - end_date (NULL-safe comparison)
        
        This prevents duplicate temporal_locations for co-residents, colleagues, classmates.
        
        Args:
            location_id: Location UUID
            start_date: Start date (partial date string like "2020" or "2020-06")
            end_date: End date (partial date string or None for current)
            is_current: Whether this is the current temporal location
            notes: Optional notes
            
        Returns:
            UUID of existing or newly created temporal_location
        """
        # Try to find existing temporal_location with same location and dates
        find_query = """
            SELECT id FROM temporal_locations
            WHERE location_id = $1
              AND (start_date = $2 OR (start_date IS NULL AND $2 IS NULL))
              AND (end_date = $3 OR (end_date IS NULL AND $3 IS NULL))
            LIMIT 1
        """
        
        existing = await self.db.fetch_one(
            find_query,
            location_id, start_date, end_date
        )
        
        if existing:
            # Found existing temporal_location - reuse it
            return existing['id']
        
        # No existing temporal_location found - create new one
        create_query = """
            INSERT INTO temporal_locations (
                location_id, start_date, end_date, is_current, notes
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """
        
        new_tl = await self.db.fetch_one(
            create_query,
            location_id, start_date, end_date, is_current, notes
        )
        
        return new_tl['id']
    
    async def create(self, person: PersonCreate) -> Person:
        """Create a new person"""
        query = """
            INSERT INTO people (canonical_name, aliases, relationship, category, kinship_to_owner)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            person.canonical_name,
            person.aliases,
            person.relationship,
            person.category,
            person.kinship_to_owner
        )
        return await self._dict_to_model(row, Person)
    
    async def get_by_id(self, person_id: UUID) -> Optional[Person]:
        """Get person by ID"""
        query = "SELECT * FROM people WHERE id = $1"
        row = await self.db.fetchrow(query, person_id)
        return await self._dict_to_model(row, Person)
    
    async def get_by_name(self, name: str, fuzzy: bool = True, include_deleted: bool = False) -> Optional[Person]:
        """Get person by name (fuzzy search supported)"""
        if fuzzy:
            query = "SELECT * FROM people WHERE canonical_name ILIKE $1"
            pattern = f"%{name}%"
        else:
            # Use ILIKE for case-insensitive exact match to prevent duplicates
            query = "SELECT * FROM people WHERE canonical_name ILIKE $1"
            pattern = name
        
        # Add deleted filter
        if not include_deleted:
            query += " AND is_deleted = FALSE"
        
        query += " LIMIT 1"
        
        row = await self.db.fetchrow(query, pattern)
        return await self._dict_to_model(row, Person)
    
    async def list_all(self, limit: int = 100, include_deleted: bool = False) -> List[Person]:
        """List all people"""
        query = "SELECT * FROM people"
        
        if not include_deleted:
            query += " WHERE is_deleted = FALSE"
        
        query += " ORDER BY canonical_name LIMIT $1"
        rows = await self.db.fetch(query, limit)
        return await self._list_to_models(rows, Person)
    
    async def get_or_create(self, name: str) -> Person:
        """Get existing person or create new one"""
        person = await self.get_by_name(name, fuzzy=False)
        if person:
            return person
        
        person_create = PersonCreate(canonical_name=name)
        return await self.create(person_create)
    
    async def create_person_full(
        self,
        canonical_name: str,
        aliases: list = None,
        relationship: str = None,
        category: str = None,
        kinship_to_owner: str = None,
        birthday = None,
        death_date = None,
        ethnicity: str = None,
        origin_location: str = None,
        known_since: Union[int, str] = None,
        last_interaction_date = None,
        google_people_id: str = None
    ) -> Person:
        """Create a person with comprehensive biographical information"""
        from models import Person
        
        # Convert int year to string if needed
        known_since_val = str(known_since) if isinstance(known_since, int) else known_since
        
        query = """
            INSERT INTO people (
                canonical_name, aliases, relationship, category, kinship_to_owner,
                birthday, death_date, ethnicity, origin_location, known_since, last_interaction_date, google_people_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            canonical_name,
            aliases or [],
            relationship,
            category,
            kinship_to_owner,
            birthday,
            death_date,
            ethnicity,
            origin_location,
            known_since_val,
            last_interaction_date,
            google_people_id
        )
        return Person(**dict(row))
    
    async def add_note(
        self,
        person_id: UUID,
        text: str,
        note_type: str = None,
        category: str = None,
        note_date = None,
        source: str = None,
        context: str = None,
        tags: list = None
    ):
        """Add a biographical note about a person"""
        query = """
            INSERT INTO person_notes (
                person_id, text, note_type, category, note_date, source, context, tags
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            person_id,
            text,
            note_type,
            category,
            note_date,
            source,
            context,
            tags or []
        )
        return dict(row)
    
    async def add_relationship(
        self,
        person_id: UUID,
        related_person_id: UUID,
        relationship_type: str,
        relationship_label: str = None,
        notes: str = None,
        bidirectional: bool = True
    ):
        """
        Add a relationship between two people.
        
        NOTE: Database triggers automatically create reciprocal relationships,
        so we only need to insert the primary relationship.
        The bidirectional parameter is kept for backward compatibility but
        the database handles creating B→A when A→B is inserted.
        """
        # Mapping of relationship types to their reverses (for return info)
        reverse_map = {
            'spouse': 'spouse',
            'parent': 'child',
            'child': 'parent',
            'sibling': 'sibling',
            'grandparent': 'grandchild',
            'grandchild': 'grandparent',
            'aunt_uncle': 'niece_nephew',
            'niece_nephew': 'aunt_uncle',
            'cousin': 'cousin',
            'other': 'other'
        }
        
        # Create primary relationship only - triggers will create reciprocal
        query = """
            INSERT INTO person_relationships (
                person_id, related_person_id, relationship_type, relationship_label, notes
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            person_id,
            related_person_id,
            relationship_type,
            relationship_label,
            notes
        )
        result = dict(row)
        
        # Add reverse type info for bidirectional relationships
        if bidirectional:
            reverse_type = reverse_map.get(relationship_type, 'other')
            result['reverse_type'] = reverse_type
        
        return result
    
    async def update_relationship(
        self,
        relationship_id: UUID,
        relationship_label: str = None,
        notes: str = None
    ) -> Dict[str, Any]:
        """Update a relationship's label and/or notes."""
        # Build dynamic UPDATE query based on provided fields
        updates = []
        params = []
        param_count = 1
        
        if relationship_label is not None:
            updates.append(f"relationship_label = ${param_count}")
            params.append(relationship_label)
            param_count += 1
        
        if notes is not None:
            updates.append(f"notes = ${param_count}")
            params.append(notes)
            param_count += 1
        
        if not updates:
            raise ValueError("At least one field (relationship_label or notes) must be provided")
        
        # Add relationship_id as last parameter
        params.append(relationship_id)
        
        query = f"""
            UPDATE person_relationships
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = ${param_count}
            RETURNING *
        """
        
        row = await self.db.fetchrow(query, *params)
        if not row:
            raise ValueError(f"Relationship not found: {relationship_id}")
        
        return dict(row)
    
    async def delete_relationship(self, relationship_id: UUID) -> Dict[str, Any]:
        """Delete a person relationship by ID. Also deletes reciprocal relationship."""
        # Get the relationship first
        rel = await self.db.fetchrow(
            'SELECT * FROM person_relationships WHERE id = $1',
            relationship_id
        )
        
        if not rel:
            raise ValueError(f"Relationship not found: {relationship_id}")
        
        result = dict(rel)
        
        # Delete this relationship
        await self.db.execute(
            'DELETE FROM person_relationships WHERE id = $1',
            relationship_id
        )
        
        # Note: The trigger on DELETE will automatically handle deleting the reciprocal
        # so we don't need to manually delete the reverse relationship
        
        return result
    
    async def update_person(
        self,
        person_id: UUID,
        canonical_name: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        relationship: Optional[str] = None,
        category: Optional[str] = None,
        kinship_to_owner: Optional[str] = None,
        birthday: Optional[date] = None,
        death_date: Optional[date] = None,
        ethnicity: Optional[str] = None,
        origin_location: Optional[str] = None,
        known_since: Optional[Union[int, str]] = None,
        last_interaction_date: Optional[date] = None,
        google_people_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update person fields. Only updates provided fields."""
        
        # Build dynamic update query
        updates = []
        params = []
        param_idx = 1
        
        if canonical_name is not None:
            updates.append(f"canonical_name = ${param_idx}")
            params.append(canonical_name)
            param_idx += 1
        
        if aliases is not None:
            updates.append(f"aliases = ${param_idx}")
            params.append(aliases)
            param_idx += 1
        
        if relationship is not None:
            updates.append(f"relationship = ${param_idx}")
            params.append(relationship)
            param_idx += 1
        
        if category is not None:
            updates.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if kinship_to_owner is not None:
            updates.append(f"kinship_to_owner = ${param_idx}")
            params.append(kinship_to_owner)
            param_idx += 1
        
        if birthday is not None:
            updates.append(f"birthday = ${param_idx}")
            params.append(birthday)
            param_idx += 1
        
        if death_date is not None:
            updates.append(f"death_date = ${param_idx}")
            params.append(death_date)
            param_idx += 1
        
        if ethnicity is not None:
            updates.append(f"ethnicity = ${param_idx}")
            params.append(ethnicity)
            param_idx += 1
        
        if origin_location is not None:
            updates.append(f"origin_location = ${param_idx}")
            params.append(origin_location)
            param_idx += 1
        
        if known_since is not None:
            # Convert int to string (YYYY format)
            known_since_val = str(known_since) if isinstance(known_since, int) else known_since
            updates.append(f"known_since = ${param_idx}")
            params.append(known_since_val)
            param_idx += 1
        
        if last_interaction_date is not None:
            updates.append(f"last_interaction_date = ${param_idx}")
            params.append(last_interaction_date)
            param_idx += 1
        
        if google_people_id is not None:
            updates.append(f"google_people_id = ${param_idx}")
            params.append(google_people_id)
            param_idx += 1
        
        # Always update updated_at
        updates.append(f"updated_at = NOW()")
        
        if not updates:
            raise ValueError("No fields to update")
        
        # Add person_id as final parameter
        params.append(person_id)
        where_param_idx = param_idx
        
        query = f"""
            UPDATE people
            SET {', '.join(updates)}
            WHERE id = ${where_param_idx}
            RETURNING *
        """
        
        row = await self.db.fetchrow(query, *params)
        if row is None:
            raise ValueError(f"Person not found: {person_id}")
        return dict(row)
    
    async def delete_person(self, person_id: UUID) -> Dict[str, Any]:
        """Soft delete a person record (mark as deleted without removing data)"""
        query = """
            UPDATE people
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, person_id)
        if row is None:
            raise ValueError(f"Person not found: {person_id}")
        return dict(row)
    
    async def undelete_person(self, person_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted person record"""
        query = """
            UPDATE people
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, person_id)
        if row is None:
            raise ValueError(f"Person not found: {person_id}")
        return dict(row)
    
    async def add_work(
        self,
        person_id: UUID,
        company: str,
        role: str,
        location_id: UUID,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        is_current: bool = False,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add work history with temporal_location support (location_id required - Design #31)."""
        
        # location_id is now required - no fallback to place_text
        if not location_id:
            raise ValueError("location_id is required - cannot use place_text (Design #31)")
        
        # Find or create temporal_location (reuses existing for colleagues)
        temporal_location_id = await self._find_or_create_temporal_location(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            notes=notes
        )
        
        # Create person_work entry
        work_query = """
            INSERT INTO person_work (
                person_id, temporal_location_id, company, role, notes
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        work_row = await self.db.fetch_one(
            work_query,
            person_id, temporal_location_id, company, role, notes
        )
        
        result = dict(work_row)
        result['temporal_location_id'] = str(temporal_location_id)
        return result
    
    async def add_education(
        self,
        person_id: UUID,
        institution: str,
        degree: str,
        location_id: UUID,
        field: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        is_current: bool = False,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add education history with temporal_location support."""
        # location_id is required under Design #31
        if not location_id:
            raise ValueError("location_id is required for education entries (Design #31)")

        # Find or create temporal_location (reuses existing for classmates)
        temporal_location_id = await self._find_or_create_temporal_location(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            notes=notes
        )
        
        # Create person_education entry
        edu_query = """
            INSERT INTO person_education (
                person_id, temporal_location_id, institution, degree, field, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
        """
        edu_row = await self.db.fetch_one(
            edu_query,
            person_id, temporal_location_id, institution, degree, field, notes
        )
        
        result = dict(edu_row)
        result['temporal_location_id'] = str(temporal_location_id)
        return result
    
    async def add_residence(
        self,
        person_id: UUID,
        location_id: UUID,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        is_current: bool = False,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add residence history with temporal_location support."""
        # location_id is required under Design #31
        if not location_id:
            raise ValueError("location_id is required for residence entries (Design #31)")

        # Find or create temporal_location (reuses existing for co-residents)
        temporal_location_id = await self._find_or_create_temporal_location(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            notes=notes
        )
        
        # Create person_residences entry
        res_query = """
            INSERT INTO person_residences (
                person_id, temporal_location_id, notes
            )
            VALUES ($1, $2, $3)
            RETURNING *
        """
        res_row = await self.db.fetch_one(
            res_query,
            person_id, temporal_location_id, notes
        )
        
        result = dict(res_row)
        result['temporal_location_id'] = str(temporal_location_id)
        return result
    
    async def add_residence_with_temporal_location(
        self,
        person_id: UUID,
        temporal_location_id: UUID,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add residence history reusing an existing temporal_location.
        
        Use this when adding residence for roommates/flatmates who shared the same
        location during the same time period (Issue #107 fix).
        
        Args:
            person_id: UUID of the person
            temporal_location_id: UUID of existing temporal_location to reuse
            notes: Optional notes about the residence
            
        Returns:
            Dict with residence record and temporal_location_id
        """
        # Verify temporal_location exists
        verify_query = "SELECT id FROM temporal_locations WHERE id = $1"
        existing = await self.db.fetch_one(verify_query, temporal_location_id)
        if not existing:
            raise ValueError(f"temporal_location_id {temporal_location_id} not found")
        
        # Create person_residences entry
        res_query = """
            INSERT INTO person_residences (
                person_id, temporal_location_id, notes
            )
            VALUES ($1, $2, $3)
            RETURNING *
        """
        res_row = await self.db.fetch_one(
            res_query,
            person_id, temporal_location_id, notes
        )
        
        result = dict(res_row)
        result['temporal_location_id'] = str(temporal_location_id)
        return result


class LocationsRepository(BaseRepository):
    """Repository for locations operations"""
    
    async def create(self, location: LocationCreate) -> Location:
        """Create a new location"""
        query = """
            INSERT INTO locations (
                canonical_name, location_type, place_id, notes
            )
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            location.canonical_name,
            location.location_type,
            location.place_id,
            location.notes
        )
        return await self._dict_to_model(row, Location)
    
    async def get_by_id(self, location_id: UUID) -> Optional[Location]:
        """Get location by ID"""
        query = "SELECT * FROM locations WHERE id = $1"
        row = await self.db.fetchrow(query, location_id)
        return await self._dict_to_model(row, Location)
    
    async def get_by_name(self, name: str, fuzzy: bool = True) -> Optional[Location]:
        """Get location by name"""
        if fuzzy:
            query = "SELECT * FROM locations WHERE canonical_name ILIKE $1 LIMIT 1"
            pattern = f"%{name}%"
        else:
            # Use ILIKE for case-insensitive exact match to prevent duplicates
            query = "SELECT * FROM locations WHERE canonical_name ILIKE $1 LIMIT 1"
            pattern = name
        
        row = await self.db.fetchrow(query, pattern)
        return await self._dict_to_model(row, Location)
    
    async def list_all(self, limit: int = 100) -> List[Location]:
        """List all locations"""
        query = "SELECT * FROM locations ORDER BY canonical_name LIMIT $1"
        rows = await self.db.fetch(query, limit)
        return await self._list_to_models(rows, Location)
    
    async def get_or_create(self, name: str, location_type: Optional[str] = None) -> Location:
        """Get existing location or create new one"""
        location = await self.get_by_name(name, fuzzy=False)
        if location:
            return location
        
        location_create = LocationCreate(canonical_name=name, location_type=location_type)
        return await self.create(location_create)
    
    async def update(
        self,
        location_id: UUID,
        canonical_name: Optional[str] = None,
        location_type: Optional[str] = None,
        place_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[Location]:
        """Update an existing location with provided fields"""
        # Build dynamic update query
        updates = []
        params = []
        param_idx = 1
        
        if canonical_name is not None:
            updates.append(f"canonical_name = ${param_idx}")
            params.append(canonical_name)
            param_idx += 1
        
        if location_type is not None:
            updates.append(f"location_type = ${param_idx}")
            params.append(location_type)
            param_idx += 1
        
        if place_id is not None:
            updates.append(f"place_id = ${param_idx}")
            params.append(place_id)
            param_idx += 1
        
        if notes is not None:
            updates.append(f"notes = ${param_idx}")
            params.append(notes)
            param_idx += 1
        
        if not updates:
            # No fields to update, just return the existing location
            return await self.get_by_id(location_id)
        
        # Add location_id as the last parameter
        params.append(location_id)
        
        query = f"""
            UPDATE locations
            SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ${param_idx}
            RETURNING *
        """
        
        row = await self.db.fetchrow(query, *params)
        return await self._dict_to_model(row, Location)
    
    async def delete(self, location_id: UUID) -> Dict[str, Any]:
        """Soft delete a location"""
        query = """
            UPDATE locations
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, location_id)
        if row is None:
            raise ValueError(f"Location not found: {location_id}")
        return dict(row)
    
    async def soft_delete(self, location_id: UUID) -> Dict[str, Any]:
        """Soft delete a location (alias for delete)"""
        return await self.delete(location_id)
    
    async def undelete(self, location_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted location"""
        query = """
            UPDATE locations
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, location_id)
        if row is None:
            raise ValueError(f"Location not found: {location_id}")
        return dict(row)


class ExercisesRepository(BaseRepository):
    """Repository for exercises operations"""
    
    async def create(self, exercise: ExerciseCreate) -> Exercise:
        """Create a new exercise"""
        query = """
            INSERT INTO exercises (
                canonical_name, category,
                primary_muscle_group,
                secondary_muscle_groups,
                equipment, variants, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            exercise.canonical_name,
            exercise.category.value,
            exercise.primary_muscle_group,
            exercise.secondary_muscle_groups,
            exercise.equipment,
            exercise.variants,
            exercise.notes
        )
        return await self._dict_to_model(row, Exercise)
    
    async def get_by_id(self, exercise_id: UUID) -> Optional[Exercise]:
        """Get exercise by ID"""
        query = "SELECT * FROM exercises WHERE id = $1"
        row = await self.db.fetchrow(query, exercise_id)
        return await self._dict_to_model(row, Exercise)
    
    async def get_by_name(self, name: str, fuzzy: bool = True) -> Optional[Exercise]:
        """Get exercise by name"""
        if fuzzy:
            query = "SELECT * FROM exercises WHERE canonical_name ILIKE $1 LIMIT 1"
            pattern = f"%{name}%"
        else:
            # Use ILIKE for case-insensitive exact match to prevent duplicates
            query = "SELECT * FROM exercises WHERE canonical_name ILIKE $1 LIMIT 1"
            pattern = name
        
        row = await self.db.fetchrow(query, pattern)
        return await self._dict_to_model(row, Exercise)
    
    async def list_all(self, limit: int = 100) -> List[Exercise]:
        """List all exercises"""
        query = "SELECT * FROM exercises ORDER BY canonical_name LIMIT $1"
        rows = await self.db.fetch(query, limit)
        return await self._list_to_models(rows, Exercise)
    
    async def list_by_category(self, category: str) -> List[Exercise]:
        """List exercises by category"""
        query = "SELECT * FROM exercises WHERE category = $1 ORDER BY canonical_name"
        rows = await self.db.fetch(query, category)
        return await self._list_to_models(rows, Exercise)
    
    async def list_by_muscle_group(self, muscle_group: str) -> List[Exercise]:
        """List exercises targeting a muscle group"""
        query = """
            SELECT * FROM exercises
            WHERE primary_muscle_group = $1
               OR $1 = ANY(secondary_muscle_groups)
            ORDER BY canonical_name
        """
        rows = await self.db.fetch(query, muscle_group)
        return await self._list_to_models(rows, Exercise)
    
    async def soft_delete(self, exercise_id: UUID) -> Dict[str, Any]:
        """Soft delete an exercise"""
        query = """
            UPDATE exercises
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, exercise_id)
        if row is None:
            raise ValueError(f"Exercise not found: {exercise_id}")
        return dict(row)
    
    async def undelete(self, exercise_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted exercise"""
        query = """
            UPDATE exercises
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, exercise_id)
        if row is None:
            raise ValueError(f"Exercise not found: {exercise_id}")
        return dict(row)


class WorkoutsRepository(BaseRepository):
    """Repository for workouts operations"""
    
    async def create(self, workout: WorkoutCreate, start_time: datetime, end_time: Optional[datetime] = None, location_id: Optional[UUID] = None) -> Workout:
        """Create a new workout with exercises and sets"""
        async with self.db.transaction():
            # First create the event
            event_query = """
                INSERT INTO events (
                    start_time, end_time, location_id, event_type
                )
                VALUES ($1, $2, $3, 'workout')
                RETURNING id
            """
            event_row = await self.db.fetchrow(
                event_query,
                start_time,
                end_time,
                location_id
            )
            event_id = event_row['id']
            
            # Now create the workout
            workout_query = """
                INSERT INTO workouts (
                    event_id, workout_name, category
                )
                VALUES ($1, $2, $3)
                RETURNING *
            """
            workout_row = await self.db.fetchrow(
                workout_query,
                event_id,
                workout.workout_name,
                workout.category.value if hasattr(workout.category, 'value') else workout.category
            )
            workout_id = workout_row['id']
            
            # Insert workout exercises and sets
            for exercise_data in workout.exercises:
                # Insert workout_exercise
                we_query = """
                    INSERT INTO workout_exercises (
                        workout_id, exercise_id, sequence_order,
                        rest_between_exercises_s, notes
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """
                we_row = await self.db.fetchrow(
                    we_query,
                    workout_id,
                    exercise_data.exercise_id,
                    exercise_data.sequence_order,
                    exercise_data.rest_between_exercises_s,
                    exercise_data.notes
                )
                we_id = we_row['id']
                
                # Insert sets
                for set_data in exercise_data.sets:
                    set_query = """
                        INSERT INTO exercise_sets (
                            workout_exercise_id, set_number, set_type,
                            weight_kg, reps, duration_s, distance_km,
                            rest_time_s, pace, notes
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """
                    await self.db.execute(
                        set_query,
                        we_id,
                        set_data.set_number,
                        set_data.set_type.value if hasattr(set_data.set_type, 'value') else set_data.set_type,
                        set_data.weight_kg,
                        set_data.reps,
                        set_data.duration_s,
                        set_data.distance_km,
                        set_data.rest_time_s,
                        set_data.pace,
                        set_data.notes
                    )
            
            # Get complete workout
            return await self.get_by_id(workout_id)
    
    async def get_by_id(self, workout_id: UUID) -> Optional[Workout]:
        """Get workout with all exercises and sets"""
        # Get workout base data with event location
        workout_query = """
            SELECT w.*, e.location_id, l.canonical_name as location_name
            FROM workouts w
            JOIN events e ON w.event_id = e.id
            LEFT JOIN locations l ON e.location_id = l.id
            WHERE w.id = $1
        """
        workout_row = await self.db.fetchrow(workout_query, workout_id)
        if not workout_row:
            return None
        
        # Get exercises
        exercises_query = """
            SELECT we.*, e.canonical_name as exercise_name
            FROM workout_exercises we
            JOIN exercises e ON we.exercise_id = e.id
            WHERE we.workout_id = $1
            ORDER BY we.sequence_order
        """
        exercise_rows = await self.db.fetch(exercises_query, workout_id)
        
        exercises = []
        for ex_row in exercise_rows:
            # Get sets for this exercise
            sets_query = """
                SELECT * FROM exercise_sets
                WHERE workout_exercise_id = $1
                ORDER BY set_number
            """
            set_rows = await self.db.fetch(sets_query, ex_row['id'])
            sets = [ExerciseSet(**dict(s)) for s in set_rows]
            
            exercises.append(WorkoutExercise(
                id=ex_row['id'],
                exercise_id=ex_row['exercise_id'],
                exercise_name=ex_row['exercise_name'],
                sequence_order=ex_row['sequence_order'],
                rest_between_exercises_s=ex_row['rest_between_exercises_s'],
                notes=ex_row['notes'],
                sets=sets
            ))
        
        # Get participants from event_participants (event-centric schema)
        participants_query = """
            SELECT ep.person_id
            FROM event_participants ep
            JOIN workouts w ON w.event_id = ep.event_id
            WHERE w.id = $1
        """
        participant_rows = await self.db.fetch(participants_query, workout_id)
        participants = [row['person_id'] for row in participant_rows]
        
        # Build workout model
        workout_dict = dict(workout_row)
        workout_dict['exercises'] = exercises
        workout_dict['participants'] = participants
        
        return Workout(**workout_dict)
    
    async def list_by_date_range(
        self,
        start_date: Union[date, str],
        end_date: Union[date, str],
        limit: int = 100
    ) -> List[Workout]:
        """List workouts in date range"""
        query = """
            SELECT w.* FROM workouts w
            JOIN events e ON w.event_id = e.id
            WHERE DATE(e.start_time) BETWEEN $1 AND $2
            ORDER BY DATE(e.start_time) DESC, e.start_time DESC
            LIMIT $3
        """
        rows = await self.db.fetch(query, start_date, end_date, limit)
        
        # Get full workout data for each
        workouts = []
        for row in rows:
            workout = await self.get_by_id(row['id'])
            if workout:
                workouts.append(workout)
        
        return workouts
    
    async def list_by_date(self, workout_date: Union[date, str]) -> List[Workout]:
        """List workouts on a specific date"""
        return await self.list_by_date_range(workout_date, workout_date)
    
    async def create_with_event(
        self,
        event: EventCreate,
        workout: WorkoutCreate
    ) -> 'WorkoutWithEvent':
        """Create workout with event (event-first pattern)"""
        from models import WorkoutWithEvent
        
        async with self.db.transaction():
            # Step 1: Create event
            events_repo = EventsRepository(self.db)
            created_event = await events_repo.create(event)
            
            # Step 2: Create workout with event_id
            workout_query = """
                INSERT INTO workouts (
                    event_id, workout_name, category, workout_subtype, sport_type
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
            """
            workout_row = await self.db.fetchrow(
                workout_query,
                created_event.id,
                workout.workout_name,
                workout.category.value if hasattr(workout.category, 'value') else workout.category,
                workout.workout_subtype.value.lower() if workout.workout_subtype and hasattr(workout.workout_subtype, 'value') else (workout.workout_subtype.lower() if workout.workout_subtype else None),
                workout.sport_type
            )
            workout_id = workout_row['id']
            
            # Step 3: Insert workout exercises and sets
            for exercise_data in workout.exercises:
                we_query = """
                    INSERT INTO workout_exercises (
                        workout_id, exercise_id, sequence_order,
                        rest_between_exercises_s, notes
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """
                we_row = await self.db.fetchrow(
                    we_query,
                    workout_id,
                    exercise_data.exercise_id,
                    exercise_data.sequence_order,
                    exercise_data.rest_between_exercises_s,
                    exercise_data.notes
                )
                we_id = we_row['id']
                
                # Insert sets
                for set_data in exercise_data.sets:
                    set_query = """
                        INSERT INTO exercise_sets (
                            workout_exercise_id, set_number, set_type,
                            weight_kg, reps, duration_s, distance_km,
                            rest_time_s, pace, interval_description,
                            work_duration_s, rest_duration_s, notes
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """
                    await self.db.execute(
                        set_query,
                        we_id,
                        set_data.set_number,
                        set_data.set_type.value if hasattr(set_data.set_type, 'value') else set_data.set_type,
                        set_data.weight_kg,
                        set_data.reps,
                        set_data.duration_s,
                        set_data.distance_km,
                        set_data.rest_time_s,
                        set_data.pace,
                        set_data.interval_description,
                        set_data.work_duration_s,
                        set_data.rest_duration_s,
                        set_data.notes
                    )
            
            # Get complete workout with exercises
            created_workout = await self.get_by_id(workout_id)
            
            return WorkoutWithEvent(event=created_event, workout=created_workout)
    
    async def delete(self, workout_id: UUID) -> Dict[str, Any]:
        """Soft delete a workout"""
        query = """
            UPDATE workouts
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, workout_id)
        if row is None:
            raise ValueError(f"Workout not found: {workout_id}")
        return dict(row)
    
    async def get_by_event_id(self, event_id: UUID) -> Optional[Workout]:
        """Get workout by event ID"""
        workout_query = "SELECT * FROM workouts WHERE event_id = $1"
        workout_row = await self.db.fetchrow(workout_query, event_id)
        if not workout_row:
            return None
        
        workout_id = workout_row['id']
        return await self.get_by_id(workout_id)
    
    async def update_workout(self, event_id: UUID, updates: dict):
        """Update workout metadata by event_id"""
        if not updates:
            raise ValueError("No updates provided")
        
        # Build SET clause dynamically
        set_clauses = []
        values = []
        param_count = 1
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1
        
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())
        
        query = f"""
            UPDATE workouts
            SET {', '.join(set_clauses)}
            WHERE event_id = ${param_count + 1}
            RETURNING id
        """
        
        values.append(event_id)
        row = await self.db.fetchrow(query, *values)
        
        if not row:
            raise ValueError(f"Workout with event_id {event_id} not found")
        
        return await self.get_by_event_id(event_id)
    
    async def undelete(self, workout_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted workout"""
        query = """
            UPDATE workouts
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, workout_id)
        if row is None:
            raise ValueError(f"Workout not found: {workout_id}")
        return dict(row)


class MealsRepository(BaseRepository):
    """Repository for meals operations"""
    
    async def create(self, meal: MealCreate, start_time: Optional[datetime] = None) -> Meal:
        """Create a new meal - requires creating an event first"""
        async with self.db.transaction():
            # First create the event
            event_query = """
                INSERT INTO events (
                    start_time, event_type
                )
                VALUES ($1, 'meal')
                RETURNING id
            """
            event_row = await self.db.fetchrow(
                event_query,
                start_time
            )
            event_id = event_row['id']
            
            # Now create the meal referencing the event
            meal_query = """
                INSERT INTO meals (
                    event_id, meal_title, meal_type, portion_size
                )
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """
            meal_row = await self.db.fetchrow(
                meal_query,
                event_id,
                meal.meal_title.value if meal.meal_title else None,
                meal.meal_type.value if meal.meal_type else None,
                meal.portion_size.value if meal.portion_size else None
            )
            meal_id = meal_row['id']
            
            return await self.get_by_id(meal_id)
    
    async def get_by_id(self, meal_id: UUID) -> Optional[Meal]:
        """Get meal from database with items"""
        meal_query = "SELECT * FROM meals WHERE id = $1"
        meal_row = await self.db.fetchrow(meal_query, meal_id)
        if not meal_row:
            return None
        
        # Fetch meal items
        items_query = "SELECT * FROM meal_items WHERE meal_id = $1 ORDER BY created_at"
        items_rows = await self.db.fetch(items_query, meal_id)
        
        from models import MealItem
        items = [MealItem(**dict(row)) for row in items_rows]
        
        meal_dict = dict(meal_row)
        meal_dict['items'] = items
        
        return Meal(**meal_dict)
    
    async def get_by_event_id(self, event_id: UUID) -> Optional[Meal]:
        """Get meal by event ID"""
        meal_query = "SELECT * FROM meals WHERE event_id = $1"
        meal_row = await self.db.fetchrow(meal_query, event_id)
        if not meal_row:
            return None
        
        meal_id = meal_row['id']
        
        # Fetch meal items
        items_query = "SELECT * FROM meal_items WHERE meal_id = $1 ORDER BY created_at"
        items_rows = await self.db.fetch(items_query, meal_id)
        
        from models import MealItem
        items = [MealItem(**dict(row)) for row in items_rows]
        
        meal_dict = dict(meal_row)
        meal_dict['items'] = items
        
        return Meal(**meal_dict)
    
    async def update(self, meal_id: UUID, updates: dict):
        """Update meal metadata by meal_id"""
        if not updates:
            raise ValueError("No updates provided")
        
        # Build SET clause dynamically
        set_clauses = []
        values = []
        param_count = 1
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1
        
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())
        
        query = f"""
            UPDATE meals
            SET {', '.join(set_clauses)}
            WHERE id = ${param_count + 1}
            RETURNING id
        """
        
        values.append(meal_id)
        row = await self.db.fetchrow(query, *values)
        
        if not row:
            raise ValueError(f"Meal with id {meal_id} not found")
        
        return await self.get_by_id(meal_id)
    
    async def update_meal(self, event_id: UUID, updates: dict):
        """Update meal metadata by event_id"""
        if not updates:
            raise ValueError("No updates provided")
        
        # Build SET clause dynamically
        set_clauses = []
        values = []
        param_count = 1
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1
        
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())
        
        query = f"""
            UPDATE meals
            SET {', '.join(set_clauses)}
            WHERE event_id = ${param_count + 1}
            RETURNING id
        """
        
        values.append(event_id)
        row = await self.db.fetchrow(query, *values)
        
        if not row:
            raise ValueError(f"Meal with event_id {event_id} not found")
        
        return await self.get_by_event_id(event_id)
    
    async def create_item(self, item: 'MealItemCreate'):
        """Create a meal item"""
        query = """
            INSERT INTO meal_items (
                meal_id, item_name, quantity
            )
            VALUES ($1, $2, $3)
            RETURNING id
        """
        row = await self.db.fetchrow(
            query,
            item.meal_id,
            item.item_name,
            item.quantity
        )
        return row['id']
    
    async def delete_items(self, event_id: UUID):
        """Delete all items for a meal (by event_id)"""
        query = """
            DELETE FROM meal_items
            WHERE meal_id = (SELECT id FROM meals WHERE event_id = $1)
        """
        await self.db.execute(query, event_id)
    
    async def list_by_date(self, meal_date: Union[date, str]) -> List[Meal]:
        """List meals on a specific date via meal_events view"""
        query = """
            SELECT m.* FROM meals m
            JOIN events e ON m.event_id = e.id
            WHERE DATE(e.start_time) = $1
            ORDER BY e.start_time
        """
        rows = await self.db.fetch(query, meal_date)
        
        return [Meal(**dict(row)) for row in rows]
    
    async def create_with_event(
        self,
        event: EventCreate,
        meal: MealCreate
    ) -> 'MealWithEvent':
        """Create meal with event (event-first pattern)"""
        from models import MealWithEvent
        
        async with self.db.transaction():
            # Step 1: Create event
            events_repo = EventsRepository(self.db)
            created_event = await events_repo.create(event)
            
            # Step 2: Create meal with event_id
            meal_query = """
                INSERT INTO meals (
                    event_id, meal_title, meal_type, portion_size
                )
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """
            meal_row = await self.db.fetchrow(
                meal_query,
                created_event.id,
                meal.meal_title.value if meal.meal_title and hasattr(meal.meal_title, 'value') else meal.meal_title,
                meal.meal_type.value if meal.meal_type and hasattr(meal.meal_type, 'value') else meal.meal_type,
                meal.portion_size.value if meal.portion_size and hasattr(meal.portion_size, 'value') else meal.portion_size
            )
            meal_id = meal_row['id']
            
            # Step 3: Insert meal items
            if meal.items:
                for idx, item in enumerate(meal.items):
                    item_query = """
                        INSERT INTO meal_items (
                            meal_id, item_name, quantity
                        )
                        VALUES ($1, $2, $3)
                        RETURNING id
                    """
                    try:
                        item_row = await self.db.fetchrow(
                            item_query,
                            meal_id,
                            item.item_name,
                            item.quantity
                        )
                        if not item_row:
                            raise RuntimeError(f"Failed to insert meal item {idx}: {item.item_name}")
                    except Exception as e:
                        raise RuntimeError(f"Error inserting meal item {idx} ({item.item_name}): {str(e)}")
            
            # Get complete meal
            created_meal = await self.get_by_id(meal_id)
            
            return MealWithEvent(event=created_event, meal=created_meal)
    
    async def delete(self, meal_id: UUID) -> Dict[str, Any]:
        """Soft delete a meal"""
        query = """
            UPDATE meals
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, meal_id)
        if row is None:
            raise ValueError(f"Meal not found: {meal_id}")
        return dict(row)
    
    async def undelete(self, meal_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted meal"""
        query = """
            UPDATE meals
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, meal_id)
        if row is None:
            raise ValueError(f"Meal not found: {meal_id}")
        return dict(row)


# Continue with other repositories...
class WorkDaysRepository(BaseRepository):
    """Repository for work days operations"""
    
    async def create(self, work_day: WorkDayCreate) -> WorkDay:
        """Create work day with blocks"""
        async with self.db.transaction():
            # Insert work day
            day_query = """
                INSERT INTO work_days (work_date, primary_location, notes)
                VALUES ($1, $2, $3)
                RETURNING *
            """
            day_row = await self.db.fetchrow(
                day_query,
                work_day.work_date,
                work_day.primary_location,
                work_day.notes
            )
            work_day_id = day_row['id']
            
            # Insert blocks
            for block in work_day.blocks:
                block_query = """
                    INSERT INTO work_blocks (
                        work_day_id, start_time, end_time,
                        location, category, work_type, productivity, notes
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """
                await self.db.execute(
                    block_query,
                    work_day_id,
                    block.start_time,
                    block.end_time,
                    block.location,
                    block.category.value,
                    block.work_type.value,
                    block.productivity.value if block.productivity else None,
                    block.notes
                )
            
            return await self.get_by_date(work_day.work_date)
    
    async def get_by_date(self, work_date: Union[date, str]) -> Optional[WorkDay]:
        """Get work day with blocks"""
        day_query = "SELECT * FROM work_days WHERE work_date = $1"
        day_row = await self.db.fetchrow(day_query, work_date)
        if not day_row:
            return None
        
        blocks_query = "SELECT * FROM work_blocks WHERE work_day_id = $1 ORDER BY start_time"
        block_rows = await self.db.fetch(blocks_query, day_row['id'])
        blocks = [WorkBlock(**dict(b)) for b in block_rows]
        
        day_dict = dict(day_row)
        day_dict['blocks'] = blocks
        
        return WorkDay(**day_dict)


class SleepSessionsRepository(BaseRepository):
    """Repository for sleep sessions"""
    
    async def create(self, sleep: SleepSessionCreate) -> SleepSession:
        """Create sleep session"""
        query = """
            INSERT INTO sleep_sessions (sleep_time, wake_time, quality, location, notes)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            sleep.sleep_time,
            sleep.wake_time,
            sleep.quality.value if sleep.quality else None,
            sleep.location,
            sleep.notes
        )
        return await self._dict_to_model(row, SleepSession)
    
    async def get_by_date(self, sleep_date: Union[date, str]) -> Optional[SleepSession]:
        """Get sleep session for date"""
        query = "SELECT * FROM sleep_sessions WHERE sleep_date = $1 LIMIT 1"
        row = await self.db.fetchrow(query, sleep_date)
        return await self._dict_to_model(row, SleepSession)


class EventsRepository(BaseRepository):
    """Repository for events"""
    
    async def create(self, event: EventCreate) -> Event:
        """
        Create event with event-centric pattern.
        
        Note: This method does NOT create its own transaction. It should be called
        from within an existing transaction context (e.g., from create_with_event methods
        that manage the transaction scope).
        """
        query = """
            INSERT INTO events (
                event_type, title, description, category, significance,
                start_time, end_time, location_id,
                parent_event_id, source_person_id, event_scope, recurrence, recurrence_end_date,
                notes, tags, external_event_id, external_event_source
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
            event.title,
            event.description,
            event.category,
            event.significance.value if hasattr(event.significance, 'value') else event.significance,
            event.start_time,
            event.end_time,
            event.location_id,
            getattr(event, 'parent_event_id', None),
            getattr(event, 'source_person_id', None),
            getattr(event, 'event_scope', 'single_day'),
            getattr(event, 'recurrence', 'none'),
            getattr(event, 'recurrence_end_date', None),
            event.notes,
            event.tags,
            getattr(event, 'external_event_id', None),
            getattr(event, 'external_event_source', None)
        )
        event_id = row['id']
        
        # Insert participants (EventParticipant objects with person_id and role)
        for participant in event.participants:
            await self.db.execute(
                "INSERT INTO event_participants (event_id, person_id, role, interaction_mode) VALUES ($1, $2, $3, $4)",
                event_id, 
                participant.person_id,
                participant.role,
                participant.interaction_mode
            )
        
        return await self.get_by_id(event_id)
    
    async def get_by_id(self, event_id: UUID) -> Optional[Event]:
        """Get event with participants"""
        query = "SELECT * FROM events WHERE id = $1"
        row = await self.db.fetchrow(query, event_id)
        if not row:
            return None
        
        # Get participants with roles
        participants_query = """
            SELECT ep.person_id, ep.role, ep.interaction_mode, p.canonical_name as person_name
            FROM event_participants ep
            LEFT JOIN people p ON ep.person_id = p.id
            WHERE ep.event_id = $1
        """
        participant_rows = await self.db.fetch(participants_query, event_id)
        participants = [
            EventParticipant(
                person_id=r['person_id'],
                person_name=r['person_name'],
                role=r['role'],
                interaction_mode=r['interaction_mode']
            ) for r in participant_rows
        ]
        
        # Get location name if location_id exists
        location_name = None
        if row['location_id']:
            loc_query = "SELECT canonical_name FROM locations WHERE id = $1"
            loc_row = await self.db.fetchrow(loc_query, row['location_id'])
            if loc_row:
                location_name = loc_row['canonical_name']
        
        event_dict = dict(row)
        event_dict['participants'] = participants
        event_dict['location_name'] = location_name
        # Convert NULL tags to empty list
        if event_dict.get('tags') is None:
            event_dict['tags'] = []
        
        return Event(**event_dict)
    
    async def list_by_date_range(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Event]:
        """List events in date range"""
        query = """
            SELECT id FROM events
            WHERE DATE(start_time) BETWEEN $1 AND $2
            AND is_deleted = FALSE
            ORDER BY DATE(start_time), start_time
        """
        rows = await self.db.fetch(query, start_date, end_date)
        
        events = []
        for row in rows:
            event = await self.get_by_id(row['id'])
            if event:
                events.append(event)
        
        return events
    
    async def delete(self, event_id: UUID) -> Dict[str, Any]:
        """Soft delete an event"""
        query = """
            UPDATE events
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, event_id)
        if row is None:
            raise ValueError(f"Event not found: {event_id}")
        return dict(row)
    
    async def soft_delete(self, event_id: UUID) -> Dict[str, Any]:
        """Soft delete an event (alias for delete)"""
        return await self.delete(event_id)
    
    async def update(self, event_id: UUID, updates: dict) -> Event:
        """Update event fields.
        
        Special handling for 'participants' key:
        - If provided, replaces all existing participants
        - Deletes old event_participants entries and inserts new ones
        """
        if not updates:
            raise ValueError("No updates provided")
        
        # Extract participants if provided (not a direct column)
        participants_list = updates.pop("participants", None)
        
        # Build SET clause dynamically for remaining fields
        set_clauses = []
        values = []
        param_count = 1
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1
        
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())
        
        query = f"""
            UPDATE events
            SET {', '.join(set_clauses)}
            WHERE id = ${param_count + 1}
            RETURNING *
        """
        
        values.append(event_id)
        row = await self.db.fetchrow(query, *values)
        
        if not row:
            raise ValueError(f"Event {event_id} not found")
        
        # Handle participant updates if provided
        if participants_list is not None:
            # Delete existing participants
            await self.db.execute(
                "DELETE FROM event_participants WHERE event_id = $1",
                event_id
            )
            
            # Insert new participants
            for participant in participants_list:
                await self.db.execute(
                    "INSERT INTO event_participants (event_id, person_id, role, interaction_mode) VALUES ($1, $2, $3, $4)",
                    event_id,
                    participant.person_id,
                    participant.role,
                    participant.interaction_mode
                )
        
        return await self.get_by_id(event_id)
    
    async def undelete(self, event_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted event"""
        query = """
            UPDATE events
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, event_id)
        if row is None:
            raise ValueError(f"Event not found: {event_id}")
        return dict(row)


class ReflectionsRepository(BaseRepository):
    """Repository for reflections (event-centric architecture)"""
    
    async def create(self, reflection_create: "ReflectionCreate"):
        """Create reflection linked to an event"""
        query = """
            INSERT INTO reflections (
                event_id, reflection_type, mood, mood_score,
                prompt_question, key_insights, action_items
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, event_id, reflection_type, mood, mood_score,
                      prompt_question, key_insights, action_items,
                      created_at, updated_at
        """
        row = await self.db.fetchrow(
            query,
            reflection_create.event_id,
            reflection_create.reflection_type,
            reflection_create.mood,
            reflection_create.mood_score,
            reflection_create.prompt_question,
            reflection_create.key_insights,
            reflection_create.action_items
        )
        return await self._dict_to_model(dict(row), Reflection)
    
    async def get_by_id(self, reflection_id: UUID):
        """Get reflection by ID"""
        query = """
            SELECT id, event_id, reflection_type, mood, mood_score,
                   prompt_question, key_insights, action_items,
                   is_deleted, created_at, updated_at
            FROM reflections
            WHERE id = $1
        """
        row = await self.db.fetchrow(query, reflection_id)
        return await self._dict_to_model(dict(row) if row else None, Reflection)
    
    async def get_by_event_id(self, event_id: UUID):
        """Get reflection by event ID"""
        query = """
            SELECT id, event_id, reflection_type, mood, mood_score,
                   prompt_question, key_insights, action_items,
                   is_deleted, created_at, updated_at
            FROM reflections
            WHERE event_id = $1 AND is_deleted = FALSE
        """
        row = await self.db.fetchrow(query, event_id)
        return await self._dict_to_model(dict(row) if row else None, Reflection)
    
    async def update(self, event_id: UUID, updates: dict):
        """Update reflection by event_id"""
        if not updates:
            raise ValueError("No updates provided")
        
        # Build SET clause dynamically
        set_clauses = []
        values = []
        param_count = 1
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1
        
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())
        
        query = f"""
            UPDATE reflections
            SET {', '.join(set_clauses)}
            WHERE event_id = ${param_count + 1}
            RETURNING id, event_id, reflection_type, mood, mood_score,
                      prompt_question, key_insights, action_items,
                      created_at, updated_at
        """
        
        values.append(event_id)
        row = await self.db.fetchrow(query, *values)
        
        if not row:
            raise ValueError(f"Reflection with event_id {event_id} not found")
        
        return await self._dict_to_model(dict(row), Reflection)


class JournalDaysRepository(BaseRepository):
    """Repository for journal days"""
    
    async def get_by_date(self, journal_date: Union[date, str]) -> Optional[JournalDay]:
        """Get journal day (auto-created by triggers)"""
        query = "SELECT * FROM journal_days WHERE journal_date = $1"
        row = await self.db.fetchrow(query, journal_date)
        return await self._dict_to_model(row, JournalDay)
    
    async def update_summary(
        self,
        journal_date: str,
        day_title: Optional[str] = None,
        day_rating: Optional[int] = None,
        highlights: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> JournalDay:
        """Update journal day summary"""
        # Ensure journal day exists
        await self.db.execute(
            "INSERT INTO journal_days (journal_date) VALUES ($1) ON CONFLICT DO NOTHING",
            journal_date
        )
        
        # Update fields
        query = """
            UPDATE journal_days
            SET day_title = COALESCE($2, day_title),
                day_rating = COALESCE($3, day_rating),
                highlights = COALESCE($4, highlights),
                notes = COALESCE($5, notes),
                updated_at = NOW()
            WHERE journal_date = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, journal_date, day_title, day_rating, highlights, notes)
        return await self._dict_to_model(row, JournalDay)


# ============================================================================
# Journal Entries Repository (NEW)
# ============================================================================


# ============================================================================
# Commutes Repository (NEW)
# ============================================================================

class CommutesRepository(BaseRepository):
    """Repository for commute/travel operations"""

    async def get_by_id(self, commute_id: UUID):
        """Get commute by ID (excludes soft-deleted records)."""
        from models import Commute

        query = "SELECT * FROM commutes WHERE id = $1 AND is_deleted = FALSE"
        row = await self.db.fetchrow(query, commute_id)
        return await self._dict_to_model(row, Commute)

    async def update(self, commute_id: UUID, updates: dict):
        """Update commute fields (excludes soft-deleted records)."""
        from models import Commute

        if not updates:
            raise ValueError("No updates provided")

        set_clauses = []
        values = []
        param_count = 1

        for key, value in updates.items():
            set_clauses.append(f"{key} = ${param_count}")
            values.append(value)
            param_count += 1

        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())

        query = f"""
            UPDATE commutes
            SET {', '.join(set_clauses)}
            WHERE id = ${param_count + 1} AND is_deleted = FALSE
            RETURNING *
        """

        values.append(commute_id)
        row = await self.db.fetchrow(query, *values)
        if not row:
            raise ValueError(f"Commute {commute_id} not found or has been deleted")

        return await self._dict_to_model(row, Commute)
    
    async def create_with_event(
        self,
        event: EventCreate,
        commute: 'CommuteCreate',
        participant_ids: Optional[List[UUID]] = None
    ) -> 'CommuteWithEvent':
        """Create commute with event (event-first pattern)"""
        from models import Commute, CommuteWithEvent
        
        async with self.db.transaction():
            # Step 1: Create event (participants are in event.participants)
            events_repo = EventsRepository(self.db)
            created_event = await events_repo.create(event)
            
            # Step 2: Create commute specialization
            query = """
                INSERT INTO commutes (
                    event_id, from_location_id, to_location_id, transport_mode
                ) VALUES ($1, $2, $3, $4)
                RETURNING *
            """
            transport_mode = commute.transport_mode.value if hasattr(commute.transport_mode, 'value') else commute.transport_mode
            
            row = await self.db.fetchrow(
                query,
                created_event.id,
                commute.from_location_id,
                commute.to_location_id,
                transport_mode
            )
            created_commute = await self._dict_to_model(row, Commute)
            
            return CommuteWithEvent(event=created_event, commute=created_commute)
    
    async def list_recent(self, limit: int = 20) -> List[Dict]:
        """List recent commutes with event data"""
        query = """
            SELECT * FROM commute_events
            ORDER BY start_time DESC
            LIMIT $1
        """
        rows = await self.db.fetch(query, limit)
        return [dict(row) for row in rows]


# ============================================================================
# Entertainment Repository (NEW)
# ============================================================================

class EntertainmentRepository(BaseRepository):
    """Repository for entertainment operations"""
    
    async def create_with_event(
        self,
        event: EventCreate,
        entertainment: 'EntertainmentCreate',
        participant_ids: Optional[List[UUID]] = None
    ) -> 'EntertainmentWithEvent':
        """Create entertainment with event (event-first pattern)"""
        from models import Entertainment, EntertainmentWithEvent
        
        async with self.db.transaction():
            # Step 1: Create event (participants are in event.participants)
            events_repo = EventsRepository(self.db)
            created_event = await events_repo.create(event)
        
        # Step 2: Create entertainment specialization
        query = """
            INSERT INTO entertainment (
                event_id, entertainment_type, title, creator, genre,
                show_name, season_number, episode_number, episode_title,
                channel_name, video_url, director, release_year,
                performance_type, venue, performer_artist,
                game_platform, game_genre, platform, format,
                personal_rating, completion_status, rewatch, watched_with_others
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
            RETURNING *
        """
        ent_type = entertainment.entertainment_type.value if hasattr(entertainment.entertainment_type, 'value') else entertainment.entertainment_type
        perf_type = entertainment.performance_type.value if entertainment.performance_type and hasattr(entertainment.performance_type, 'value') else entertainment.performance_type
        comp_status = entertainment.completion_status.value if hasattr(entertainment.completion_status, 'value') else entertainment.completion_status
        
        row = await self.db.fetchrow(
            query,
            created_event.id,
            ent_type,
            entertainment.title,
            entertainment.creator,
            entertainment.genre,
            entertainment.show_name,
            entertainment.season_number,
            entertainment.episode_number,
            entertainment.episode_title,
            entertainment.channel_name,
            entertainment.video_url,
            entertainment.director,
            entertainment.release_year,
            perf_type,
            entertainment.venue,
            entertainment.performer_artist,
            entertainment.game_platform,
            entertainment.game_genre,
            entertainment.platform,
            entertainment.format,
            entertainment.personal_rating,
            comp_status,
            entertainment.rewatch,
            entertainment.watched_with_others
        )
        created_entertainment = await self._dict_to_model(row, Entertainment)
        
        return EntertainmentWithEvent(event=created_event, entertainment=created_entertainment)
    
    async def list_recent(self, limit: int = 20) -> List[Dict]:
        """List recent entertainment with event data"""
        query = """
            SELECT * FROM media_events
            ORDER BY start_time DESC
            LIMIT $1
        """
        rows = await self.db.fetch(query, limit)
        return [dict(row) for row in rows]


# ============================================================================
# HEALTH TRACKING REPOSITORIES
# ============================================================================

class HealthConditionRepository(BaseRepository):
    """Repository for health conditions (illnesses and injuries)"""
    
    def _parse_date_string(self, date_str: Optional[str]) -> Optional[date]:
        """Convert partial or full date string to date object.
        
        For partial dates (YYYY or YYYY-MM), uses first day of period.
        For full dates (YYYY-MM-DD), parses directly.
        Returns None for None input.
        """
        if not date_str:
            return None
        
        if len(date_str) == 4:  # YYYY
            return date(int(date_str), 1, 1)
        elif len(date_str) == 7:  # YYYY-MM
            return date(int(date_str[:4]), int(date_str[5:7]), 1)
        elif len(date_str) == 10:  # YYYY-MM-DD
            return date.fromisoformat(date_str)
        else:
            raise ValueError(f"Invalid date string format: {date_str}")
    
    async def create_with_event(
        self,
        event: EventCreate,
        condition: 'HealthConditionCreate',
        person_id: Optional[UUID] = None
    ) -> 'HealthConditionWithEvent':
        """Create health condition with event (event-first pattern)

        Args:
            event: Event to create
            condition: Health condition to create
            person_id: Optional person UUID (defaults to owner if not provided)
        """
        from models import HealthCondition, HealthConditionWithEvent

        # If person_id not provided in condition or parameter, resolve to owner
        resolved_person_id = person_id or condition.person_id
        if not resolved_person_id:
            # Get owner person_id from database
            owner_query = "SELECT person_id FROM owner LIMIT 1"
            owner_result = await self.db.fetchrow(owner_query)
            if not owner_result:
                raise ValueError("Owner not configured in database")
            resolved_person_id = owner_result['person_id']

        # Validate person exists
        person_check = await self.db.fetchrow(
            "SELECT id FROM people WHERE id = $1", resolved_person_id
        )
        if not person_check:
            raise ValueError(f"Person {resolved_person_id} not found")

        # Step 1: Create event
        events_repo = EventsRepository(self.db)
        created_event = await events_repo.create(event)

        # Step 2: Add person as event participant
        await self.db.execute(
            """INSERT INTO event_participants (event_id, person_id, role)
               VALUES ($1, $2, $3)""",
            created_event.id, resolved_person_id, 'affected'
        )

        # Step 3: Create health condition with person_id
        query = """
            INSERT INTO health_conditions (
                event_id, person_id, condition_type, condition_name, severity, severity_score,
                is_sport_related, sport_type, start_date, end_date, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """

        cond_type = condition.condition_type.value if hasattr(condition.condition_type, 'value') else condition.condition_type
        severity_val = condition.severity.value if condition.severity and hasattr(condition.severity, 'value') else condition.severity

        # Convert date strings to date objects for PostgreSQL
        start_date_obj = self._parse_date_string(condition.start_date)
        end_date_obj = self._parse_date_string(condition.end_date)

        row = await self.db.fetchrow(
            query,
            created_event.id,
            resolved_person_id,
            cond_type,
            condition.condition_name,
            severity_val,
            condition.severity_score,
            condition.is_sport_related,
            condition.sport_type,
            start_date_obj,
            end_date_obj,
            condition.notes
        )

        created_condition = await self._dict_to_model(row, HealthCondition)

        return HealthConditionWithEvent(event=created_event, condition=created_condition)
    
    async def get_by_id(self, condition_id: UUID) -> Optional[Dict]:
        """Get health condition by ID"""
        query = "SELECT * FROM health_conditions WHERE id = $1"
        row = await self.db.fetchrow(query, condition_id)
        return dict(row) if row else None

    async def get_by_person_id(
        self,
        person_id: UUID,
        include_deleted: bool = False
    ) -> List[Dict]:
        """Get all health conditions for a specific person.

        Args:
            person_id: UUID of the person
            include_deleted: Whether to include soft-deleted conditions

        Returns:
            List of health condition dicts
        """
        query = """
            SELECT * FROM health_conditions
            WHERE person_id = $1
        """

        if not include_deleted:
            query += " AND is_deleted = FALSE"

        query += " ORDER BY start_date DESC, created_at DESC"

        rows = await self.db.fetch(query, person_id)
        return [dict(row) for row in rows]

    async def list_by_date_range(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """List health conditions within a date range"""
        query = """
            SELECT * FROM health_conditions
            WHERE start_date <= $2 AND (end_date >= $1 OR end_date IS NULL)
            AND is_deleted = FALSE
            ORDER BY start_date DESC
        """
        rows = await self.db.fetch(query, start_date, end_date)
        return [dict(row) for row in rows]
    
    async def delete(self, condition_id: UUID) -> Dict[str, Any]:
        """Soft delete a health condition"""
        query = """
            UPDATE health_conditions
            SET is_deleted = TRUE, deleted_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, condition_id)
        if row is None:
            raise ValueError(f"Health condition not found: {condition_id}")
        return dict(row)
    
    async def undelete(self, condition_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted health condition"""
        query = """
            UPDATE health_conditions
            SET is_deleted = FALSE, deleted_at = NULL
            WHERE id = $1
            RETURNING *
        """
        row = await self.db.fetchrow(query, condition_id)
        if row is None:
            raise ValueError(f"Health condition not found: {condition_id}")
        return dict(row)


class HealthConditionLogsRepository(BaseRepository):
    """Repository for health condition progression logs"""

    async def create(self, log: 'HealthConditionLogCreate') -> Dict:
        """Create a condition progression log entry"""
        from datetime import datetime

        # Get person_id from parent condition if not provided
        person_id = log.person_id
        if not person_id:
            parent_condition = await self.db.fetchrow(
                "SELECT person_id FROM health_conditions WHERE id = $1",
                log.condition_id
            )
            if parent_condition:
                person_id = parent_condition['person_id']

        query = """
            INSERT INTO health_condition_logs (
                condition_id, person_id, log_date, severity, severity_score, notes
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
        """
        log_date_obj = datetime.strptime(log.log_date, '%Y-%m-%d').date() if log.log_date else None
        severity_val = log.severity.value if log.severity else None

        row = await self.db.fetchrow(
            query,
            log.condition_id,
            person_id,
            log_date_obj,
            severity_val,
            log.severity_score,
            log.notes
        )
        return dict(row) if row else None

    async def get_by_id(self, log_id: UUID) -> Optional[Dict]:
        """Get log entry by ID"""
        query = "SELECT * FROM health_condition_logs WHERE id = $1"
        row = await self.db.fetchrow(query, log_id)
        return dict(row) if row else None

    async def delete(self, log_id: UUID) -> Dict:
        """Soft delete a condition log entry"""
        query = """
            UPDATE health_condition_logs
            SET is_deleted = TRUE, deleted_at = NOW()
            WHERE id = $1 AND is_deleted = FALSE
            RETURNING *
        """
        row = await self.db.fetchrow(query, log_id)
        if not row:
            raise ValueError(f"Health condition log not found or already deleted: {log_id}")
        return dict(row)

    async def undelete(self, log_id: UUID) -> Dict:
        """Restore a soft-deleted condition log entry"""
        query = """
            UPDATE health_condition_logs
            SET is_deleted = FALSE, deleted_at = NULL
            WHERE id = $1 AND is_deleted = TRUE
            RETURNING *
        """
        row = await self.db.fetchrow(query, log_id)
        if not row:
            raise ValueError(f"Health condition log not found or not deleted: {log_id}")
        return dict(row)


class HealthMedicineRepository(BaseRepository):
    """Repository for medicines taken"""
    
    async def create(self, medicine: 'HealthMedicineCreate') -> Dict:
        """Create medicine log entry"""
        from datetime import datetime
        
        query = """
            INSERT INTO health_medicines (
                event_id, condition_id, medicine_name, dosage, dosage_unit,
                frequency, log_date, log_time, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """
        
        # Convert log_date string to date object
        log_date_obj = None
        if medicine.log_date:
            # Parse YYYY-MM-DD format (full date)
            if len(medicine.log_date) == 10:
                log_date_obj = datetime.strptime(medicine.log_date, '%Y-%m-%d').date()
            else:
                raise ValueError(f"log_date must be full date (YYYY-MM-DD) for medicine logging, got: {medicine.log_date}")
        
        row = await self.db.fetchrow(
            query,
            medicine.event_id,
            medicine.condition_id,
            medicine.medicine_name,
            medicine.dosage,
            medicine.dosage_unit,
            medicine.frequency,
            log_date_obj,
            medicine.log_time,
            medicine.notes
        )
        
        return dict(row) if row else None
    
    async def get_by_id(self, medicine_id: UUID) -> Optional[Dict]:
        """Get medicine by ID"""
        query = "SELECT * FROM health_medicines WHERE id = $1"
        row = await self.db.fetchrow(query, medicine_id)
        return dict(row) if row else None
    
    async def list_by_date_range(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """List medicines within a date range"""
        query = """
            SELECT * FROM health_medicines
            WHERE log_date BETWEEN $1 AND $2
            ORDER BY log_date DESC, log_time DESC
        """
        rows = await self.db.fetch(query, start_date, end_date)
        return [dict(row) for row in rows]
    
    async def list_by_condition(self, condition_id: UUID) -> List[Dict]:
        """List medicines for a specific condition"""
        query = """
            SELECT * FROM health_medicines
            WHERE condition_id = $1
            ORDER BY log_date DESC, log_time DESC
        """
        rows = await self.db.fetch(query, condition_id)
        return [dict(row) for row in rows]


class HealthSupplementRepository(BaseRepository):
    """Repository for dietary supplements"""
    
    async def create(self, supplement: 'HealthSupplementCreate') -> Dict:
        """Create supplement log entry"""
        from datetime import datetime
        
        query = """
            INSERT INTO health_supplements (
                event_id, supplement_name, amount, amount_unit,
                frequency, log_date, log_time, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """
        
        # Convert log_date string to date object
        log_date_obj = None
        if supplement.log_date:
            # Parse YYYY-MM-DD format (full date)
            if len(supplement.log_date) == 10:
                log_date_obj = datetime.strptime(supplement.log_date, '%Y-%m-%d').date()
            else:
                raise ValueError(f"log_date must be full date (YYYY-MM-DD) for supplement logging, got: {supplement.log_date}")
        
        row = await self.db.fetchrow(
            query,
            supplement.event_id,
            supplement.supplement_name,
            supplement.amount,
            supplement.amount_unit,
            supplement.frequency,
            log_date_obj,
            supplement.log_time,
            supplement.notes
        )
        
        return dict(row) if row else None
    
    async def get_by_id(self, supplement_id: UUID) -> Optional[Dict]:
        """Get supplement by ID"""
        query = "SELECT * FROM health_supplements WHERE id = $1"
        row = await self.db.fetchrow(query, supplement_id)
        return dict(row) if row else None
    
    async def list_by_date_range(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """List supplements within a date range"""
        query = """
            SELECT * FROM health_supplements
            WHERE log_date BETWEEN $1 AND $2
            ORDER BY log_date DESC, log_time DESC
        """
        rows = await self.db.fetch(query, start_date, end_date)
        return [dict(row) for row in rows]
    
    async def list_by_name(self, supplement_name: str) -> List[Dict]:
        """List all logs for a specific supplement"""
        query = """
            SELECT * FROM health_supplements
            WHERE LOWER(supplement_name) = LOWER($1)
            ORDER BY log_date DESC, log_time DESC
        """
        rows = await self.db.fetch(query, supplement_name)
        return [dict(row) for row in rows]

class JournalRepository(BaseRepository):
    """Repository for raw journal entries"""
    
    async def create(self, entry: JournalEntryCreate) -> JournalEntry:
        """Create a new journal entry"""
        
        # Convert entry_date to date object
        entry_date_val = date.today()
        if entry.entry_date:
            if isinstance(entry.entry_date, str):
                try:
                    # Try YYYY-MM-DD
                    entry_date_val = datetime.strptime(entry.entry_date, "%Y-%m-%d").date()
                except ValueError:
                    # If partial date (YYYY or YYYY-MM), we might default to 1st of month/year
                    # But for now, let's just keep today if parsing fails, or maybe raise error
                    pass
            elif isinstance(entry.entry_date, date):
                entry_date_val = entry.entry_date

        query = """
            INSERT INTO journal_entries (
                raw_text, entry_date, entry_type, tags
            )
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """
        row = await self.db.fetchrow(
            query,
            entry.raw_text,
            entry_date_val,
            entry.entry_type,
            entry.tags
        )
        return JournalEntry(**dict(row))
        
    async def get_by_date(self, date: date) -> List[JournalEntry]:
        """Get all entries for a specific date (excludes deleted)"""
        query = """
            SELECT * FROM journal_entries
            WHERE entry_date = $1 AND deleted_at IS NULL
            ORDER BY created_at ASC
        """
        rows = await self.db.fetch(query, date)
        return [JournalEntry(**dict(row)) for row in rows]
        
    async def get_by_id(self, entry_id: UUID) -> Optional[JournalEntry]:
        """Get entry by ID"""
        query = "SELECT * FROM journal_entries WHERE id = $1"
        row = await self.db.fetchrow(query, entry_id)
        if row:
            return JournalEntry(**dict(row))
        return None
    
    async def delete_entry(self, entry_id: UUID) -> Dict[str, Any]:
        """Soft delete a journal entry"""
        query = """
            UPDATE journal_entries
            SET is_deleted = TRUE, deleted_at = NOW(), updated_at = NOW()
            WHERE id = $1 AND is_deleted = FALSE
            RETURNING *
        """
        row = await self.db.fetchrow(query, entry_id)
        if not row:
            raise ValueError(f"Journal entry not found or already deleted: {entry_id}")
        return dict(row)
    
    async def undelete_entry(self, entry_id: UUID) -> Dict[str, Any]:
        """Restore a soft-deleted journal entry"""
        query = """
            UPDATE journal_entries
            SET is_deleted = FALSE, deleted_at = NULL, updated_at = NOW()
            WHERE id = $1 AND is_deleted = TRUE
            RETURNING *
        """
        row = await self.db.fetchrow(query, entry_id)
        if not row:
            raise ValueError(f"Journal entry not found or not deleted: {entry_id}")
        return dict(row)
