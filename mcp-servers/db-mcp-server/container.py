"""
Repository Container - Centralized dependency injection container

This module provides a single source of truth for repository initialization,
ensuring consistency across all transport modes (stdio, HTTP, etc.).
"""

from repositories import (
    PeopleRepository, LocationsRepository, ExercisesRepository,
    WorkoutsRepository, MealsRepository, EventsRepository,
    ReflectionsRepository, JournalDaysRepository,
    CommutesRepository, EntertainmentRepository,
    HealthConditionRepository, HealthConditionLogsRepository,
    HealthMedicineRepository, HealthSupplementRepository,
    JournalRepository
)
from services.memory_service import MemoryService
from config import MemoryConfig


class RepositoryContainer:
    """
    Container for repository instances with attribute access.
    
    This is the single source of truth for all repository initialization.
    Used by both stdio (server.py) and HTTP (transport/http.py) modes.
    """
    def __init__(self, db):
        self.people = PeopleRepository(db)
        self.locations = LocationsRepository(db)
        self.exercises = ExercisesRepository(db)
        self.workouts = WorkoutsRepository(db)
        self.meals = MealsRepository(db)
        self.events = EventsRepository(db)
        self.reflections = ReflectionsRepository(db)
        self.journal_days = JournalDaysRepository(db)
        self.commutes = CommutesRepository(db)
        self.entertainment = EntertainmentRepository(db)
        self.health_conditions = HealthConditionRepository(db)
        self.health_condition_logs = HealthConditionLogsRepository(db)
        self.health_medicines = HealthMedicineRepository(db)
        self.health_supplements = HealthSupplementRepository(db)
        self.journal = JournalRepository(db)
        
        # Initialize Memory Service (RAG) — vectors stored in PostgreSQL via pgvector
        self.memory = MemoryService(self.journal, db, MemoryConfig.from_environment())

