"""
Test configuration for database and MCP server
Creates isolated test database separate from production
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
# Prioritize .env.test for tests
env_test_path = Path(__file__).parent.parent / '.env.test'
env_path = Path(__file__).parent.parent / '.env'

if env_test_path.exists():
    load_dotenv(env_test_path)
elif env_path.exists():
    load_dotenv(env_path)

# Test Database Configuration
# Uses a separate test database to avoid affecting production data
TEST_DB_CONFIG = {
    'host': os.getenv('TEST_DB_HOST', 'localhost'),
    'port': int(os.getenv('TEST_DB_PORT', '5432')),
    # Prefer DB_NAME (used by DatabaseConfig.from_environment('test')) so that
    # test database creation/drop matches the DB that the app actually connects to.
    'database': os.getenv('DB_NAME', os.getenv('TEST_DB_NAME', 'personal_journal_test')),
    'user': os.getenv('TEST_DB_USER', os.getenv('DB_USER', 'postgres')),
    'password': os.getenv('TEST_DB_PASSWORD', os.getenv('DB_PASSWORD', '')),
}

# Test database connection string
TEST_DATABASE_URL = f"postgresql://{TEST_DB_CONFIG['user']}:{TEST_DB_CONFIG['password']}@{TEST_DB_CONFIG['host']}:{TEST_DB_CONFIG['port']}/{TEST_DB_CONFIG['database']}"

# Schema file location
SCHEMA_FILE = Path(__file__).parent.parent / 'schema.sql'

# Test data
SAMPLE_PERSON_NAME = "Test Person"
SAMPLE_LOCATION_NAME = "Test Gym"
SAMPLE_EXERCISE_NAME = "Test Bench Press"
