"""
Database configuration for PostgreSQL
Supports local development, testing, and Azure deployment
Environment-aware configuration based on APP_ENV
"""

import os
from dataclasses import dataclass
from typing import Optional, Literal
from urllib.parse import quote_plus
from pathlib import Path
from dotenv import load_dotenv

# Environment modes
EnvironmentMode = Literal["development", "test", "production"]

def load_app_environment(mode: Optional[str] = None) -> str:
    """
    Load environment variables from the appropriate .env file.
    
    Priority:
    1. Explicit 'mode' argument
    2. APP_ENV environment variable
    3. Default to 'development'
    
    Loads .env.{mode} if it exists, falling back to .env
    """
    if not mode:
        mode = os.getenv('APP_ENV', 'development')
    
    # Determine file path
    base_path = Path(__file__).parent
    env_file = base_path / f'.env.{mode}'
    
    if env_file.exists():
        print(f"Loading config from {env_file}")
        # override=False allows environment variables from the host (e.g., server manager)
        # to take precedence over .env file values.
        load_dotenv(env_file, override=False)
    else:
        print(f"Warning: No config file found for mode '{mode}' at {env_file}")
        
    return mode


def get_backup_root() -> Path:
    r"""
    Get the root directory for database backups.
    
    Storage by Environment:
    - Development: ./backups (local to project for convenience)
    - Test: ./backups_test (isolated test backups)
    - Production: Platform-specific user data directory
      * Windows: %LOCALAPPDATA%\JournalMCP\backups
      * Linux/Mac: ~/.local/share/journal-mcp/backups
    
    This ensures:
    - Development: Easy access and debugging
    - Production: Proper separation of code and data
    - Multi-user: Each user has isolated backups
    """
    mode = get_environment_mode()
    
    if mode == 'production':
        # Production: Use platform-specific user data directory
        if os.name == 'nt':  # Windows
            base = os.getenv('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local'))
            return Path(base) / 'JournalMCP' / 'backups'
        else:  # Linux/Mac
            base = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
            return Path(base) / 'journal-mcp' / 'backups'
    elif mode == 'test':
        # Test: Use test-specific directory
        return Path(__file__).parent / "backups_test"
    else:
        # Development: Use local directory
        return Path(__file__).parent / "backups"


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration"""
    
    host: str
    port: int
    database: str
    user: str
    password: str
    
    # Connection pool settings
    min_pool_size: int = 2
    max_pool_size: int = 10
    command_timeout: int = 60  # seconds
    
    # SSL settings (required for Azure)
    ssl_mode: str = "require"
    ssl_root_cert: Optional[str] = None
    
    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string"""
        return (
            f"postgresql://{self.user}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}"
            f"?sslmode={self.ssl_mode}"
        )
    
    @property
    def asyncpg_dsn(self) -> str:
        """Get asyncpg DSN format"""
        return (
            f"postgresql://{self.user}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    
    @classmethod
    def from_environment(cls, mode: Optional[EnvironmentMode] = None) -> 'DatabaseConfig':
        """
        Load configuration from environment variables
        
        Environment variables:
        - APP_ENV: Environment mode (development, test, production)
        - DB_HOST: Database host (default: localhost)
        - DB_PORT: Database port (default: 5432)
        - DB_NAME: Database name (default: journal_db)
        - DB_USER: Database user
        - DB_PASSWORD: Database password
        - DB_SSL_MODE: SSL mode (default: require)
        
        Args:
            mode: Override environment mode (default: reads from APP_ENV)
        """
        # Ensure environment is loaded
        mode = load_app_environment(mode)
        
        # Create config from standard DB_* variables
        # Note: .env.test should set DB_NAME=personal_journal_test directly
        config = cls(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            database=os.getenv('DB_NAME', 'journal_db'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            ssl_mode=os.getenv('DB_SSL_MODE', 'prefer' if mode == 'development' else 'require'),
            min_pool_size=int(os.getenv('DB_MIN_POOL_SIZE', '2')),
            max_pool_size=int(os.getenv('DB_MAX_POOL_SIZE', '10')),
        )
        
        # Safety check
        config.validate_safety(mode)
        
        return config
        
    def validate_safety(self, mode: str):
        """Ensure configuration is safe for the requested mode"""
        if mode == 'test':
            if 'test' not in self.database and self.database != 'personal_journal_test':
                raise ValueError(f"SAFETY ERROR: Test mode requested but database is '{self.database}'. Test database must contain 'test'.")
            if 'prod' in self.database:
                raise ValueError(f"SAFETY ERROR: Test mode requested but database '{self.database}' appears to be production.")
                
        if mode == 'production':
            if self.ssl_mode != 'require':
                # Just a warning for now, or enforce strictness
                pass
    
    @classmethod
    def for_local_development(cls) -> 'DatabaseConfig':
        """Configuration for local PostgreSQL instance"""
        return cls(
            host='localhost',
            port=5432,
            database='journal_db',
            user='postgres',
            password='postgres',
            ssl_mode='prefer',  # Less strict for local
            min_pool_size=2,
            max_pool_size=5,
        )
    
    @classmethod
    def for_testing(cls) -> 'DatabaseConfig':
        """Configuration for test PostgreSQL database"""
        return cls(
            host='localhost',
            port=5432,
            database='personal_journal_test',
            user='postgres',
            password='postgres',
            ssl_mode='prefer',
            min_pool_size=2,
            max_pool_size=10,
        )
    
    @classmethod
    def for_azure(
        cls,
        server_name: str,
        database_name: str,
        admin_user: str,
        admin_password: str
    ) -> 'DatabaseConfig':
        """
        Configuration for Azure Database for PostgreSQL
        
        Args:
            server_name: Azure server name (e.g., 'myserver')
            database_name: Database name
            admin_user: Admin username
            admin_password: Admin password
        
        Returns:
            DatabaseConfig configured for Azure
        """
        # Azure PostgreSQL uses format: server.postgres.database.azure.com
        host = f"{server_name}.postgres.database.azure.com"
        
        return cls(
            host=host,
            port=5432,
            database=database_name,
            user=admin_user,
            password=admin_password,
            ssl_mode='require',  # Azure requires SSL
            min_pool_size=2,
            max_pool_size=20,
        )


# Utility functions
def get_environment_mode() -> EnvironmentMode:
    """Get current environment mode from APP_ENV variable"""
    mode = os.getenv('APP_ENV', 'development').lower()
    if mode not in ('development', 'test', 'production'):
        mode = 'development'
    return mode  # type: ignore


def is_test_mode() -> bool:
    """Check if running in test mode"""
    return get_environment_mode() == 'test'


def is_production_mode() -> bool:
    """Check if running in production mode"""
    return get_environment_mode() == 'production'


def get_query_mode() -> str:
    """
    Get the query mode for read operations.

    Modes:
    - 'sql': Legacy mode — exposes execute_sql_query + get_database_schema (LLM writes raw SQL)
    - 'structured': New mode — exposes query + aggregate tools (structured input, server generates SQL)

    Set via QUERY_MODE environment variable. Default: 'sql'
    """
    mode = os.getenv('QUERY_MODE', 'sql').lower()
    if mode not in ('sql', 'structured'):
        mode = 'sql'
    return mode


def is_structured_query_mode() -> bool:
    """Check if structured query language is enabled"""
    return get_query_mode() == 'structured'


# Example .env file content
ENV_TEMPLATE = """
# Application Environment
# Options: development, test, production
APP_ENV=development

# Database Configuration (Development/Production)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=journal_db
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_SSL_MODE=prefer

# Test Database Configuration (Optional - only used when APP_ENV=test)
# Defaults to 'personal_journal_test' database with same credentials as above
# TEST_DB_HOST=localhost
# TEST_DB_PORT=5432
# TEST_DB_NAME=personal_journal_test
# TEST_DB_USER=postgres
# TEST_DB_PASSWORD=your_password_here

# Azure Production (comment out local, uncomment these)
# APP_ENV=production
# DB_HOST=your-server.postgres.database.azure.com
# DB_PORT=5432
# DB_NAME=journal_db
# DB_USER=your_admin_user
# DB_PASSWORD=your_admin_password
# DB_SSL_MODE=require

# Connection Pool Settings
DB_MIN_POOL_SIZE=2
DB_MAX_POOL_SIZE=10
"""


def create_env_file(filepath: str = ".env"):
    """Create a template .env file"""
    with open(filepath, 'w') as f:
        f.write(ENV_TEMPLATE)
    print(f"Created template .env file at {filepath}")


if __name__ == "__main__":
    # Test configuration loading
    print("Testing database configuration...")
    print(f"Environment mode: {get_environment_mode()}")
    print()
    
    # Try loading from environment
    try:
        config = DatabaseConfig.from_environment()
        print(f"✅ Loaded from environment: {config.host}:{config.port}/{config.database}")
        print(f"   SSL mode: {config.ssl_mode}")
    except Exception as e:
        print(f"⚠️  Could not load from environment: {e}")
    
    print()
    
    # Show all config variants
    print("Configuration variants:")
    print(f"Development: {DatabaseConfig.for_local_development().database}")
    print(f"Test:        {DatabaseConfig.for_testing().database}")
    print(f"From env:    {DatabaseConfig.from_environment().database}")

@dataclass
class MemoryConfig:
    """
    Configuration for the Memory/RAG system (pgvector + local embeddings).

    Vectors are stored in the journal_entries.embedding column on Azure PostgreSQL.
    No separate vector database is needed.

    Environment Variables:
    - MEMORY_ENABLED: Enable/disable semantic search (default: true)
    - EMBEDDING_MODEL: SentenceTransformer model name (default: all-MiniLM-L6-v2, 384 dims)
    """
    enabled: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @classmethod
    def from_environment(cls) -> "MemoryConfig":
        enabled_str = os.getenv("MEMORY_ENABLED", "true").lower()
        return cls(
            enabled=enabled_str in ("true", "1", "yes"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        )
