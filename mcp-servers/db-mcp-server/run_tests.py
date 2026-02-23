#!/usr/bin/env python3
"""
Test runner for Personal Journal MCP Server
Sets up test database, runs all tests, and reports results
Automatically sets APP_ENV=test to use test database configuration
"""

import sys
import os
import asyncio
from pathlib import Path
import subprocess

# Set environment to TEST mode before importing anything
os.environ['APP_ENV'] = 'test'

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_config import TEST_DB_CONFIG


def print_header(message: str):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70 + "\n")


def print_section(message: str):
    """Print formatted section"""
    print(f"\n{'─' * 70}")
    print(f"  {message}")
    print(f"{'─' * 70}\n")


async def check_postgres_connection():
    """Check if PostgreSQL is accessible"""
    print_section("Checking PostgreSQL Connection")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password'],
            database='postgres',
            ssl='prefer'  # Use prefer for local PostgreSQL
        )
        
        version = await conn.fetchval('SELECT version()')
        await conn.close()
        
        print(f"✓ PostgreSQL is accessible")
        print(f"  Version: {version.split(',')[0]}")
        print(f"  Host: {TEST_DB_CONFIG['host']}:{TEST_DB_CONFIG['port']}")
        return True
        
    except Exception as e:
        print(f"✗ Cannot connect to PostgreSQL")
        print(f"  Error: {str(e)}")
        print(f"\n  Make sure PostgreSQL is running and credentials are correct in .env")
        print(f"  Test database config: {TEST_DB_CONFIG}")
        return False


async def setup_test_database():
    """Create and setup test database"""
    print_section("Setting Up Test Database")
    
    try:
        from tests.test_fixtures import TestDatabase
        
        db = TestDatabase()
        
        # Create database
        print("Creating test database...")
        await db.create_database()
        
        # Load schema
        print("Loading database schema...")
        await db.setup_schema()
        
        # Test connection
        print("Testing connection...")
        await db.connect()
        await db.disconnect()
        
        print(f"\n✓ Test database ready: {TEST_DB_CONFIG['database']}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to setup test database")
        print(f"  Error: {str(e)}")
        return False


def run_pytest(test_path: str = None, verbose: bool = True):
    """Run pytest with specified options"""
    
    cmd = ["pytest"]
    
    if test_path:
        cmd.append(test_path)
    else:
        cmd.append("tests/")
    
    if verbose:
        cmd.append("-v")
    
    # Add other options
    cmd.extend([
        "--tb=short",          # Short traceback format
        "-s",                   # Don't capture output
        "--disable-warnings",   # Disable warnings for cleaner output
    ])
    
    print(f"Running: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd)
    return result.returncode == 0


def run_coverage_tests():
    """Run tests with coverage reporting"""
    print_section("Running Tests with Coverage")
    
    cmd = [
        "pytest",
        "tests/",
        "-v",
        "--cov=.",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--tb=short"
    ]
    
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✓ Coverage report generated in htmlcov/index.html")
    
    return result.returncode == 0


async def cleanup_test_database():
    """Drop test database"""
    print_section("Cleaning Up Test Database")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            host=TEST_DB_CONFIG['host'],
            port=TEST_DB_CONFIG['port'],
            user=TEST_DB_CONFIG['user'],
            password=TEST_DB_CONFIG['password'],
            database='postgres',
            ssl='prefer'  # Use prefer for local PostgreSQL
        )
        
        # Terminate connections
        await conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TEST_DB_CONFIG['database']}'
              AND pid <> pg_backend_pid()
        """)
        
        # Drop database
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_CONFIG['database']}")
        await conn.close()
        
        print(f"✓ Test database dropped: {TEST_DB_CONFIG['database']}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to cleanup test database")
        print(f"  Error: {str(e)}")
        return False


async def main():
    """Main test runner"""
    
    print_header("Personal Journal MCP Server - Test Suite")
    
    # Confirm test mode is set
    print(f"Environment: {os.environ.get('APP_ENV', 'unknown')}")
    print(f"Test database: {TEST_DB_CONFIG['database']}\n")
    
    # Check command line arguments
    run_coverage = "--coverage" in sys.argv
    cleanup_only = "--cleanup" in sys.argv
    setup_only = "--setup-only" in sys.argv
    test_path = None
    
    # Extract test path if provided
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            test_path = arg
            break
    
    # Cleanup only mode
    if cleanup_only:
        print("Cleanup mode: Dropping test database")
        success = await cleanup_test_database()
        sys.exit(0 if success else 1)
    
    # Step 1: Check PostgreSQL
    if not await check_postgres_connection():
        sys.exit(1)
    
    # Step 2: Setup test database
    if not await setup_test_database():
        sys.exit(1)
    
    # Exit if setup only
    if setup_only:
        print_section("Setup Complete")
        print("Test database is ready. Run tests with: python run_tests.py")
        sys.exit(0)
    
    # Step 3: Run tests
    print_section("Running Test Suite")
    
    if run_coverage:
        success = run_coverage_tests()
    else:
        success = run_pytest(test_path)
    
    # Step 4: Summary
    print_section("Test Summary")
    
    if success:
        print("✓ All tests passed!")
        print(f"\nTest database: {TEST_DB_CONFIG['database']}")
        print("  - Database is still running for inspection")
        print("  - Run 'python run_tests.py --cleanup' to drop it")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        print(f"\nTest database: {TEST_DB_CONFIG['database']}")
        print("  - Database is still running for debugging")
        print("  - Run 'python run_tests.py --cleanup' to drop it")
        sys.exit(1)


def print_usage():
    """Print usage information"""
    print("""
Usage: python run_tests.py [options] [test_path]

Options:
  --setup-only      Setup test database and exit (don't run tests)
  --cleanup         Drop test database and exit
  --coverage        Run tests with coverage reporting
  
Examples:
  python run_tests.py                           # Run all tests
  python run_tests.py tests/test_mcp_server.py  # Run specific test file
  python run_tests.py --coverage                # Run with coverage
  python run_tests.py --setup-only              # Just setup database
  python run_tests.py --cleanup                 # Drop test database

Environment:
  Test database configuration is read from .env file or defaults to:
  - Host: {TEST_DB_CONFIG['host']}
  - Port: {TEST_DB_CONFIG['port']}
  - Database: {TEST_DB_CONFIG['database']}
  - User: {TEST_DB_CONFIG['user']}
  
  You can override with TEST_DB_* environment variables.
""")


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print_usage()
        sys.exit(0)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest run interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
