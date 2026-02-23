#!/usr/bin/env python3
"""
Show current database configuration based on APP_ENV
Useful for verifying configuration before running server or tests
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from config import DatabaseConfig, get_environment_mode, is_test_mode, is_production_mode


def main():
    """Display current database configuration"""
    
    print("=" * 70)
    print("  Database Configuration")
    print("=" * 70)
    print()
    
    # Show environment
    env_mode = get_environment_mode()
    print(f"Environment Mode: {env_mode.upper()}")
    print(f"  - Test mode: {is_test_mode()}")
    print(f"  - Production mode: {is_production_mode()}")
    print()
    
    # Show APP_ENV variable
    print(f"APP_ENV variable: {os.getenv('APP_ENV', '(not set)')}")
    print()
    
    # Load configuration
    config = DatabaseConfig.from_environment()
    
    print("Active Configuration:")
    print(f"  Host:     {config.host}")
    print(f"  Port:     {config.port}")
    print(f"  Database: {config.database}")
    print(f"  User:     {config.user}")
    print(f"  SSL Mode: {config.ssl_mode}")
    print(f"  Min Pool: {config.min_pool_size}")
    print(f"  Max Pool: {config.max_pool_size}")
    print()
    
    # Show connection string (without password)
    dsn = config.asyncpg_dsn
    safe_dsn = dsn.split('@')[1] if '@' in dsn else dsn
    print(f"Connection: postgresql://***@{safe_dsn}")
    print()
    
    # Show all mode configurations
    print("=" * 70)
    print("  Available Configurations")
    print("=" * 70)
    print()
    
    for mode in ['development', 'test', 'production']:
        mode_config = DatabaseConfig.from_environment(mode=mode)
        print(f"{mode.upper()}:")
        print(f"  Database: {mode_config.database}")
        print(f"  Host:     {mode_config.host}")
        print(f"  SSL:      {mode_config.ssl_mode}")
        print()
    
    # Usage hints
    print("=" * 70)
    print("  Usage")
    print("=" * 70)
    print()
    print("Set environment mode:")
    print("  export APP_ENV=development  # Use development database")
    print("  export APP_ENV=test         # Use test database")
    print("  export APP_ENV=production   # Use production database")
    print()
    print("Or in .env file:")
    print("  APP_ENV=development")
    print()
    print("Run server:")
    print("  python server.py            # Uses APP_ENV setting")
    print()
    print("Run tests:")
    print("  python run_tests.py         # Automatically uses test mode")
    print()


if __name__ == "__main__":
    main()
