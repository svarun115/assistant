"""
Test fixtures and utilities for creating sample data
"""

import asyncio
from datetime import datetime, date, time, timedelta
from uuid import UUID, uuid4
from typing import Dict, Any, List
import asyncpg

from .test_config import TEST_DB_CONFIG, SCHEMA_FILE


class DatabaseFixture:
    """Manages test database lifecycle"""
    
    def __init__(self):
        self.pool = None
        self.config = TEST_DB_CONFIG
    
    async def create_database(self):
        """Create test database if it doesn't exist"""
        # Connect to postgres database to create test database
        sys_conn = await asyncpg.connect(
            host=self.config['host'],
            port=self.config['port'],
            user=self.config['user'],
            password=self.config['password'],
            database='postgres',
            ssl='prefer'  # Use prefer for local PostgreSQL
        )
        
        try:
            # Drop existing test database if it exists
            await sys_conn.execute(f'DROP DATABASE IF EXISTS {self.config["database"]}')
            # Create fresh test database
            await sys_conn.execute(f'CREATE DATABASE {self.config["database"]}')
            print(f"[OK] Created test database: {self.config['database']}")
        finally:
            await sys_conn.close()
    
    async def setup_schema(self):
        """Load schema into test database"""
        conn = await asyncpg.connect(
            host=self.config['host'],
            port=self.config['port'],
            user=self.config['user'],
            password=self.config['password'],
            database=self.config['database'],
            ssl='prefer'  # Use prefer for local PostgreSQL
        )
        
        try:
            # Read and execute schema
            with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            await conn.execute(schema_sql)
            print(f"[OK] Loaded schema from {SCHEMA_FILE}")
        finally:
            await conn.close()
    
    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            host=self.config['host'],
            port=self.config['port'],
            user=self.config['user'],
            password=self.config['password'],
            database=self.config['database'],
            min_size=2,
            max_size=10,
            ssl='prefer'  # Use prefer for local PostgreSQL
        )
        print(f"[OK] Connected to test database")
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print(f"[OK] Disconnected from test database")
    
    async def drop_database(self):
        """Drop the test database (cleanup after test)"""
        if self.pool:
            await self.pool.close()
            self.pool = None
        
        sys_conn = await asyncpg.connect(
            host=self.config['host'],
            port=self.config['port'],
            user=self.config['user'],
            password=self.config['password'],
            database='postgres',
            ssl='prefer'
        )
        
        try:
            await sys_conn.execute(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{self.config["database"]}'
                  AND pid <> pg_backend_pid()
            """)
            await sys_conn.execute(f'DROP DATABASE IF EXISTS {self.config["database"]}')
        finally:
            await sys_conn.close()
    
    async def cleanup(self):
        """Clean all data from test database"""
        if not self.pool:
            return
        
        try:
            conn = await self.pool.acquire()
            try:
                # Disable triggers temporarily
                await conn.execute('SET session_replication_role = replica')
                
                # Delete all data (order matters due to foreign keys)
                tables = [
                    'exercise_sets', 'workout_exercises', 'workout_participants',
                    'meal_participants', 'work_blocks',
                    'event_participants', 'event_workouts', 'event_meals',
                    'reflection_events', 'reflection_workouts', 'reflection_people',
                    'workouts', 'meals', 'work_days', 'sleep_sessions',
                    'events', 'reflections', 'journal_days',
                    'people', 'locations', 'exercises'
                ]
                
                for table in tables:
                    await conn.execute(f'DELETE FROM {table}')
                
                # Re-enable triggers
                await conn.execute('SET session_replication_role = DEFAULT')
            finally:
                # Release connection back to pool
                await self.pool.release(conn)
            
            print(f"[OK] Cleaned test database")
        except Exception as e:
            # If cleanup fails during teardown, just log it and continue
            print(f"⚠ Cleanup warning: {e}")


class SampleDataFactory:
    """Factory for creating sample test data"""
    
    def __init__(self, pool):
        self.pool = pool
        self.people_cache = {}
        self.locations_cache = {}
        self.exercises_cache = {}
    
    async def create_person(self, name: str = "John Doe", **kwargs) -> UUID:
        """Create a test person"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO people (canonical_name, relationship, category)
                VALUES ($1, $2, $3)
                RETURNING id
            """, 
                name,
                kwargs.get('relationship', 'friend'),
                kwargs.get('category', 'friend')  # Use valid enum: friend, not 'test'
            )
            person_id = row['id']
            self.people_cache[name] = person_id
            return person_id
    
    async def create_location(self, name: str = "Test Gym", **kwargs) -> UUID:
        """Create a test location"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO locations (
                    canonical_name, location_type, place_id, notes
                )
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
                name,
                kwargs.get('location_type', 'gym'),
                kwargs.get('place_id'),
                kwargs.get('notes')  # Don't provide default notes, allow NULL
            )
            location_id = row['id']
            self.locations_cache[name] = location_id
            return location_id
    
    async def create_exercise(self, name: str = "Bench Press", **kwargs) -> UUID:
        """Create a test exercise"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO exercises (
                    canonical_name, category, primary_muscle_group,
                    equipment, variants, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (canonical_name) DO UPDATE
                SET canonical_name = EXCLUDED.canonical_name
                RETURNING id
            """,
                name,
                kwargs.get('category', 'strength'),
                kwargs.get('primary_muscle_group', 'chest'),
                kwargs.get('equipment', ['barbell', 'bench']),
                kwargs.get('variants', []),
                kwargs.get('notes', 'Test exercise')
            )

            if row is None:
                row = await conn.fetchrow(
                    "SELECT id FROM exercises WHERE canonical_name = $1",
                    name,
                )
                if row is None:
                    raise RuntimeError(f"Failed to create or find exercise: {name}")

            exercise_id = row['id']
            self.exercises_cache[name] = exercise_id
            return exercise_id
    
    async def create_workout(self, **kwargs) -> UUID:
        """Create a test workout with exercises and sets"""
        workout_date = kwargs.get('workout_date', date.today())
        start_time = kwargs.get('start_time', datetime.combine(workout_date, time(9, 0)))
        end_time = kwargs.get('end_time', datetime.combine(workout_date, time(10, 0)))
        
        # Ensure we have required references
        location_id = kwargs.get('location_id')
        if not location_id and 'Test Gym' in self.locations_cache:
            location_id = self.locations_cache['Test Gym']
        elif not location_id:
            location_id = await self.create_location()
        
        async with self.pool.acquire() as conn:
            # First create event
            event_row = await conn.fetchrow("""
                INSERT INTO events (
                    start_time, end_time, location_id, event_type
                )
                VALUES ($1, $2, $3, 'workout')
                RETURNING id
            """,
                start_time,
                end_time,
                location_id
            )
            event_id = event_row['id']
            
            # Create workout
            workout_row = await conn.fetchrow("""
                INSERT INTO workouts (
                    event_id, workout_name, category
                )
                VALUES ($1, $2, $3)
                RETURNING id
            """,
                event_id,
                kwargs.get('workout_name', 'Test Workout'),
                kwargs.get('category', 'STRENGTH')  # Use uppercase for WorkoutCategory enum
            )
            workout_id = workout_row['id']
            
            # Add exercises if provided
            exercises = kwargs.get('exercises', [])
            for i, exercise_data in enumerate(exercises, 1):
                exercise_id = exercise_data.get('exercise_id')
                if not exercise_id:
                    exercise_id = await self.create_exercise(f"Exercise {i}")
                
                # Create workout_exercise
                we_row = await conn.fetchrow("""
                    INSERT INTO workout_exercises (
                        workout_id, exercise_id, sequence_order, notes
                    )
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                """, workout_id, exercise_id, i, exercise_data.get('notes'))
                
                we_id = we_row['id']
                
                # Add sets
                sets = exercise_data.get('sets', [])
                for set_num, set_data in enumerate(sets, 1):
                    await conn.execute("""
                        INSERT INTO exercise_sets (
                            workout_exercise_id, set_number, set_type,
                            weight_kg, reps, notes
                        )
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                        we_id,
                        set_num,
                        set_data.get('set_type', 'WORKING'),
                        set_data.get('weight_kg', 100.0),
                        set_data.get('reps', 10),
                        set_data.get('notes')
                    )
            
            return workout_id
    
    async def create_meal(self, **kwargs) -> UUID:
        """Create a test meal with event"""
        meal_date = kwargs.get('meal_date', date.today())
        meal_time = kwargs.get('meal_time', datetime.combine(meal_date, time(12, 0)))
        
        async with self.pool.acquire() as conn:
            # First create event (event_date is generated from start_time)
            event_row = await conn.fetchrow("""
                INSERT INTO events (
                    start_time, event_type
                )
                VALUES ($1, 'meal')
                RETURNING id
            """,
                meal_time
            )
            event_id = event_row['id']
            
            # Create meal
            meal_row = await conn.fetchrow("""
                INSERT INTO meals (
                    event_id, meal_title, meal_type, portion_size
                )
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """,
                event_id,
                kwargs.get('meal_title', 'lunch'),
                kwargs.get('meal_type', 'home_cooked'),
                kwargs.get('portion_size', 'regular')
            )
            meal_id = meal_row['id']
            
            return meal_id
    
    async def create_event(self, **kwargs) -> UUID:
        """Create a test event"""
        event_date = kwargs.get('start_date', date.today())
        start_time = kwargs.get('start_time', datetime.combine(event_date, time(10, 0)))
        end_time = kwargs.get('end_time', datetime.combine(event_date, time(11, 0)))
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO events (
                    event_type, start_time, end_time, title, description,
                    category, significance, event_scope,
                    notes, tags
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """,
                kwargs.get('event_type', 'generic'),
                start_time,
                end_time,
                kwargs.get('title', 'Test Event'),
                kwargs.get('description', 'Test event description'),
                kwargs.get('category', 'health'),
                kwargs.get('significance', 'routine'),
                kwargs.get('event_scope', 'single_day'),
                kwargs.get('notes', 'Test event'),
                kwargs.get('tags', ['test'])
            )
            return row['id']
    
    async def create_complete_day(self, target_date: date = None) -> Dict[str, Any]:
        """Create a complete day with workout, meals, and event"""
        if target_date is None:
            target_date = date.today()
        
        # Create workout
        workout_id = await self.create_workout(
            workout_date=target_date,
            exercises=[
                {
                    'sets': [
                        {'weight_kg': 100, 'reps': 10},
                        {'weight_kg': 100, 'reps': 9},
                        {'weight_kg': 100, 'reps': 8}
                    ]
                }
            ]
        )
        
        # Create meals
        breakfast_id = await self.create_meal(
            meal_date=target_date,
            meal_title='breakfast',
            meal_time=datetime.combine(target_date, time(8, 0))
        )
        
        lunch_id = await self.create_meal(
            meal_date=target_date,
            meal_title='lunch',
            meal_time=datetime.combine(target_date, time(12, 0))
        )
        
        dinner_id = await self.create_meal(
            meal_date=target_date,
            meal_title='dinner',
            meal_time=datetime.combine(target_date, time(19, 0))
        )
        
        # Create event
        event_id = await self.create_event(
            title=f'Workout Day - {target_date}',
            start_date=target_date
        )
        
        return {
            'date': target_date,
            'workout_id': workout_id,
            'breakfast_id': breakfast_id,
            'lunch_id': lunch_id,
            'dinner_id': dinner_id,
            'event_id': event_id
        }
    
    async def create_comprehensive_sample_data(self) -> Dict[str, Any]:
        """Create comprehensive sample data covering all major entities"""
        today = date.today()
        
        # Create people
        people = {}
        people['Alice'] = await self.create_person('Alice Smith', relationship='friend', category='friend')
        people['Bob'] = await self.create_person('Bob Johnson', relationship='colleague', category='work')
        people['Sarah'] = await self.create_person('Sarah Williams', relationship='family', category='family')
        
        # Create locations
        locations = {}
        locations['gym'] = await self.create_location('Local Gym', location_type='gym')
        locations['home'] = await self.create_location('Home', location_type='residence')
        locations['cafe'] = await self.create_location('Coffee Shop', location_type='cafe')
        locations['park'] = await self.create_location('Central Park', location_type='park')
        
        # Create exercises
        exercises = {}
        exercises['bench_press'] = await self.create_exercise(
            'Bench Press', 
            category='strength',
            primary_muscle_group='chest',
            equipment=['barbell', 'bench']
        )
        exercises['squat'] = await self.create_exercise(
            'Squat',
            category='strength', 
            primary_muscle_group='legs',
            equipment=['barbell', 'rack']
        )
        exercises['deadlift'] = await self.create_exercise(
            'Deadlift',
            category='strength',
            primary_muscle_group='back',
            equipment=['barbell']
        )
        exercises['running'] = await self.create_exercise(
            'Running',
            category='cardio',
            primary_muscle_group='legs',
            equipment=[]
        )
        
        # Create workouts over the past week
        workouts = []
        for days_ago in range(7):
            workout_date = today - timedelta(days=days_ago)
            workout_id = await self.create_workout(
                workout_date=workout_date,
                workout_name=f'Push Day - {workout_date}',
                location_id=locations['gym'],
                exercises=[
                    {
                        'exercise_id': exercises['bench_press'],
                        'sets': [
                            {'weight_kg': 100.0, 'reps': 10},
                            {'weight_kg': 100.0, 'reps': 9},
                            {'weight_kg': 100.0, 'reps': 8},
                        ]
                    }
                ]
            )
            workouts.append(workout_id)
        
        # Create meals over the past week
        meals = []
        for days_ago in range(7):
            meal_date = today - timedelta(days=days_ago)
            
            # Breakfast
            breakfast = await self.create_meal(
                meal_date=meal_date,
                meal_title='breakfast',
                meal_time=datetime.combine(meal_date, time(8, 0)),
                meal_type='home_cooked'
            )
            meals.append(breakfast)
            
            # Lunch
            lunch = await self.create_meal(
                meal_date=meal_date,
                meal_title='lunch',
                meal_time=datetime.combine(meal_date, time(12, 30)),
                meal_type='restaurant'
            )
            meals.append(lunch)
            
            # Dinner
            dinner = await self.create_meal(
                meal_date=meal_date,
                meal_title='dinner',
                meal_time=datetime.combine(meal_date, time(19, 0)),
                meal_type='home_cooked'
            )
            meals.append(dinner)
        
        # Create various events
        events = []
        for days_ago in range(5):
            event_date = today - timedelta(days=days_ago)
            
            # Generic event (social is category, not event_type)
            social_event = await self.create_event(
                title=f'Coffee with friends - {event_date}',
                start_time=datetime.combine(event_date, time(15, 0)),
                end_time=datetime.combine(event_date, time(16, 30)),
                category='social',
                event_type='generic',  # Use 'generic' for social events
                tags=['social', 'friends']
            )
            events.append(social_event)
        
        return {
            'people': people,
            'locations': locations,
            'exercises': exercises,
            'workouts': workouts,
            'meals': meals,
            'events': events,
            'summary': {
                'people_count': len(people),
                'locations_count': len(locations),
                'exercises_count': len(exercises),
                'workouts_count': len(workouts),
                'meals_count': len(meals),
                'events_count': len(events)
            }
        }


# Alias for backwards compatibility
TestDatabase = DatabaseFixture
