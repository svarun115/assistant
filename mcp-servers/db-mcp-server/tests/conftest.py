"""
Pytest configuration and shared fixtures for Journal MCP Server tests

APPROACH: Use DatabaseConnection directly (no wrapper layer)
- Each test gets a fresh database and connection pool
- Complete test isolation (no shared state)
- Tests use the same DatabaseConnection that handlers use in production
- Simpler, more maintainable test fixtures
"""

import pytest
from pathlib import Path
import sys
import asyncpg

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import DatabaseConnection
from config import DatabaseConfig
from container import RepositoryContainer
from tests.test_config import TEST_DB_CONFIG
from tests.test_fixtures import SampleDataFactory


SCHEMA_FILE = Path(__file__).parent.parent / "schema.sql"


def pytest_configure(config):
    """
    Pytest hook called before test collection.
    """
    # Mark that we're in test mode
    import os
    os.environ['PYTEST_RUNNING'] = '1'
    # Disable Memory/RAG by default in tests to avoid heavyweight model downloads.
    # Tests that require it should explicitly enable it via env vars.
    os.environ.setdefault('MEMORY_ENABLED', '0')


async def _create_test_database():
    """Create test database"""
    sys_conn = await asyncpg.connect(
        host=TEST_DB_CONFIG['host'],
        port=TEST_DB_CONFIG['port'],
        user=TEST_DB_CONFIG['user'],
        password=TEST_DB_CONFIG['password'],
        database='postgres',
        ssl='prefer'
    )
    
    try:
        # Drop existing test database if it exists
        await sys_conn.execute(f'DROP DATABASE IF EXISTS {TEST_DB_CONFIG["database"]}')
        # Create fresh test database
        await sys_conn.execute(f'CREATE DATABASE {TEST_DB_CONFIG["database"]}')
        print(f"[OK] Created test database: {TEST_DB_CONFIG['database']}")
    finally:
        await sys_conn.close()


async def _setup_schema():
    """Load schema into test database"""
    conn = await asyncpg.connect(
        host=TEST_DB_CONFIG['host'],
        port=TEST_DB_CONFIG['port'],
        user=TEST_DB_CONFIG['user'],
        password=TEST_DB_CONFIG['password'],
        database=TEST_DB_CONFIG['database'],
        ssl='prefer'
    )
    
    try:
        # Read and execute schema
        with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        await conn.execute(schema_sql)
        print(f"[OK] Loaded schema from {SCHEMA_FILE}")
    finally:
        await conn.close()


async def _drop_test_database():
    """Drop the test database"""
    sys_conn = await asyncpg.connect(
        host=TEST_DB_CONFIG['host'],
        port=TEST_DB_CONFIG['port'],
        user=TEST_DB_CONFIG['user'],
        password=TEST_DB_CONFIG['password'],
        database='postgres',
        ssl='prefer'
    )
    
    try:
        await sys_conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TEST_DB_CONFIG["database"]}'
              AND pid <> pg_backend_pid()
        """)
        await sys_conn.execute(f'DROP DATABASE IF EXISTS {TEST_DB_CONFIG["database"]}')
    finally:
        await sys_conn.close()


@pytest.fixture(scope="function")
async def db_connection():
    """
    DatabaseConnection fixture for use with handlers.
    
    This is the ONLY database fixture needed - it provides exactly what handlers use:
    - A DatabaseConnection object (same as production)
    - A fresh test database for each test
    - No wrapper layers or indirection
    
    All tests should use this fixture to match production code paths.
    """
    # Create database and schema
    await _create_test_database()
    await _setup_schema()
    
    # Create DatabaseConfig using from_environment for test mode
    # This correctly sets ssl_mode='prefer' for test databases
    config = DatabaseConfig.from_environment('test')
    
    # Create DatabaseConnection
    db = DatabaseConnection(config)
    await db.connect()
    
    yield db
    
    # Teardown
    await db.disconnect()
    await _drop_test_database()


@pytest.fixture(scope="function")
async def sample_data(db_connection):
    """
    Provides a SampleDataFactory for creating test data.
    Uses the same database as db_connection.
    """
    factory = SampleDataFactory(db_connection.pool)
    yield factory


@pytest.fixture(scope="function")
async def db_conn(db_connection):
    """
    Backwards compatibility fixture - just returns db_connection.
    Use db_connection instead in new tests.
    """
    yield db_connection


@pytest.fixture(scope="function")
async def db(db_connection):
    """
    Backwards compatibility fixture - just returns db_connection.
    Some tests request 'db' instead of 'db_connection'.
    """
    yield db_connection


@pytest.fixture(scope="function")
async def repos(db_connection):
    """
    Provides a RepositoryContainer initialized with the test database.
    """
    return RepositoryContainer(db_connection)

