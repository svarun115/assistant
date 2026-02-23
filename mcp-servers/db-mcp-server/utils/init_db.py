"""
Database initialization and migration script
Run this to set up the database schema
"""

import asyncio
import logging
import sys
from pathlib import Path
import subprocess

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from database import DatabaseConnection, DatabaseMigration
from config import DatabaseConfig
from backup.backup_utils import backup_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def initialize_database(config: DatabaseConfig, force: bool = False):
    """Initialize database with schema"""
    logger.info("Starting database initialization...")
    
    # Connect to database
    db = DatabaseConnection(config)
    await db.connect()
    
    try:
        # Check if schema exists
        migration = DatabaseMigration(db)
        
        if await migration.check_schema_exists():
            logger.warning("⚠️  Database schema already exists!")
            
            # Try to backup before reset
            logger.warning("🔄 Creating automatic backup before reset...")
            backup_success = False
            try:
                backup_file = backup_database()
                logger.info(f"✅ Backup created: {backup_file}")
                backup_success = True
            except Exception as e:
                logger.warning(f"⚠️  Backup skipped: {e}")
                if not force:
                    logger.error("Cannot proceed without backup confirmation. Use --force to skip backup.")
                    return
                else:
                    logger.warning("Proceeding without backup (--force flag used)")
            
            if not force:
                response = input("Do you want to recreate the schema? This will DELETE ALL DATA! (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("Aborted.")
                    return
            
            logger.warning("Dropping existing schema...")
            await db.execute("DROP SCHEMA public CASCADE")
            await db.execute("CREATE SCHEMA public")
            logger.info("Schema dropped.")
        
        # Apply schema
        schema_file = Path(__file__).parent.parent / "schema.sql"
        await migration.apply_schema(str(schema_file))
        
        logger.info("✅ Database initialized successfully!")
        
        # Show statistics
        tables = await db.get_all_tables()
        logger.info(f"Created {len(tables)} tables:")
        for table in tables:
            logger.info(f"  - {table}")
        
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        raise
    finally:
        await db.disconnect()


async def seed_sample_data(config: DatabaseConfig):
    """Seed database with sample data for testing"""
    logger.info("Seeding sample data...")
    
    from repositories import (
        PeopleRepository,
        LocationsRepository,
        ExercisesRepository,
    )
    from models import (
        PersonCreate,
        LocationCreate,
        ExerciseCreate,
        ExerciseCategory,
    )
    
    db = DatabaseConnection(config)
    await db.connect()
    
    try:
        # Sample people
        people_repo = PeopleRepository(db)
        sample_people = [
            PersonCreate(canonical_name="Gauri", relationship="partner"),
            PersonCreate(canonical_name="Anmol", relationship="friend"),
            PersonCreate(canonical_name="Divya", relationship="friend"),
        ]
        for person in sample_people:
            await people_repo.create(person)
        logger.info(f"✅ Created {len(sample_people)} sample people")
        
        # Sample locations
        locations_repo = LocationsRepository(db)
        sample_locations = [
            LocationCreate(canonical_name="Central Park", location_type="park", is_workout_location=True),
            LocationCreate(canonical_name="Home Gym", location_type="gym", is_workout_location=True),
            LocationCreate(canonical_name="Office", location_type="office"),
        ]
        for location in sample_locations:
            await locations_repo.create(location)
        logger.info(f"✅ Created {len(sample_locations)} sample locations")
        
        # Sample exercises
        exercises_repo = ExercisesRepository(db)
        sample_exercises = [
            ExerciseCreate(
                canonical_name="Bench Press",
                category=ExerciseCategory.STRENGTH,
                family="PRESS",
                primary_muscle_group="Chest",
                secondary_muscle_groups=["Triceps", "Shoulders"]
            ),
            ExerciseCreate(
                canonical_name="Squat",
                category=ExerciseCategory.STRENGTH,
                family="SQUAT",
                primary_muscle_group="Quads",
                secondary_muscle_groups=["Glutes", "Hamstrings"]
            ),
            ExerciseCreate(
                canonical_name="Running",
                category=ExerciseCategory.CARDIO,
                primary_muscle_group="Legs"
            ),
        ]
        for exercise in sample_exercises:
            await exercises_repo.create(exercise)
        logger.info(f"✅ Created {len(sample_exercises)} sample exercises")
        
        logger.info("✅ Sample data seeded successfully!")
        
    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}")
        raise
    finally:
        await db.disconnect()


async def main():
    """Main entry point"""
    # Load configuration
    try:
        config = DatabaseConfig.from_environment()
        logger.info(f"Connecting to: {config.host}:{config.port}/{config.database}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.info("Make sure you have a .env file or environment variables set.")
        sys.exit(1)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        force = "--force" in sys.argv or "-f" in sys.argv
        
        if command == "init":
            await initialize_database(config, force=force)
        elif command == "seed":
            await seed_sample_data(config)
        elif command == "reset":
            await initialize_database(config, force=force)
            await seed_sample_data(config)
        else:
            logger.error(f"Unknown command: {command}")
            print("Usage: python init_db.py [init|seed|reset] [--force]")
            sys.exit(1)
    else:
        print("Usage: python init_db.py [command] [--force]")
        print("\nCommands:")
        print("  init   - Initialize database schema")
        print("  seed   - Seed sample data")
        print("  reset  - Drop and recreate schema with sample data")
        print("\nOptions:")
        print("  --force, -f  - Skip confirmation prompt and force recreate")


if __name__ == "__main__":
    asyncio.run(main())
