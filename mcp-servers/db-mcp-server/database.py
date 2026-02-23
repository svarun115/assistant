"""
Database connection management and utilities
Async PostgreSQL operations using asyncpg
"""

import asyncpg
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from config import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Manages PostgreSQL connection pool and provides database operations
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
        
    async def connect(self):
        """Initialize connection pool"""
        if self.pool is not None:
            logger.warning("Connection pool already initialized")
            return
        
        try:
            # Configure SSL based on ssl_mode setting
            # asyncpg expects: True (require SSL), False (disable SSL), or 'prefer' (try SSL, fallback to non-SSL)
            if self.config.ssl_mode == 'require':
                ssl_setting = True
            elif self.config.ssl_mode == 'disable':
                ssl_setting = False
            else:  # 'prefer' or any other mode
                ssl_setting = 'prefer'

            async def _init_connection(conn):
                from pgvector.asyncpg import register_vector
                await register_vector(conn)

            self.pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=self.config.min_pool_size,
                max_size=self.config.max_pool_size,
                command_timeout=self.config.command_timeout,
                ssl=ssl_setting,
                init=_init_connection,
            )

            logger.info(f"✅ Connected to PostgreSQL at {self.config.host}:{self.config.port}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool with automatic error handling.
        
        Usage:
            async with db.acquire() as conn:
                result = await conn.fetch("SELECT * FROM users")
        
        Note: The connection is automatically returned to the pool even if
        an exception occurs, and the pool validates the connection state.
        """
        if self.pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        # Use asyncpg's pool.acquire() context manager properly
        async with self.pool.acquire() as connection:
            try:
                yield connection
            except Exception as e:
                # Log the error but let it propagate
                logger.error(f"Error during database operation: {e}", exc_info=True)
                # Try to reset the connection to a clean state before it's released
                try:
                    await connection.reset()
                except Exception as reset_error:
                    logger.error(f"Failed to reset connection: {reset_error}")
                raise
    
    async def execute(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> str:
        """
        Execute a query without returning results
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
            
        Returns:
            Status string (e.g., "INSERT 0 1")
        """
        async with self.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)
    
    async def fetch(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> List[asyncpg.Record]:
        """
        Fetch multiple rows
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
            
        Returns:
            List of records
        """
        async with self.acquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)
    
    async def fetchrow(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Optional[asyncpg.Record]:
        """
        Fetch a single row
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
            
        Returns:
            Single record or None
        """
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)
    
    async def fetch_one(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Optional[asyncpg.Record]:
        """
        Fetch a single row (alias for fetchrow)
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
            
        Returns:
            Single record or None
        """
        return await self.fetchrow(query, *args, timeout=timeout)
    
    async def fetchval(
        self,
        query: str,
        *args,
        column: int = 0,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Fetch a single value
        
        Args:
            query: SQL query
            *args: Query parameters
            column: Column index to return
            timeout: Query timeout in seconds
            
        Returns:
            Single value
        """
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args, column=column, timeout=timeout)
    
    async def execute_many(
        self,
        query: str,
        args_list: List[tuple],
        timeout: Optional[float] = None
    ):
        """
        Execute a query multiple times with different parameters
        
        Args:
            query: SQL query
            args_list: List of parameter tuples
            timeout: Query timeout in seconds
        """
        async with self.acquire() as conn:
            await conn.executemany(query, args_list, timeout=timeout)
    
    @asynccontextmanager
    async def transaction(self):
        """
        Execute operations within a transaction
        
        Usage:
            async with db.transaction():
                await db.execute("INSERT INTO ...")
                await db.execute("UPDATE ...")
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                # Temporarily store the connection for nested operations
                old_pool = self.pool
                
                # Create a mock pool that returns this connection
                class SingleConnectionPool:
                    @asynccontextmanager
                    async def acquire(self):
                        yield conn
                
                try:
                    self.pool = SingleConnectionPool()
                    yield conn
                finally:
                    self.pool = old_pool
    
    async def check_connection(self) -> bool:
        """
        Check if database connection is healthy
        
        Returns:
            True if connection is healthy
        """
        try:
            result = await self.fetchval("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics for monitoring.
        
        Returns:
            Dictionary with pool stats (size, free connections, etc.)
        """
        if self.pool is None:
            return {
                'status': 'disconnected',
                'size': 0,
                'freesize': 0
            }
        
        return {
            'status': 'connected',
            'size': self.pool.get_size(),
            'freesize': self.pool.get_idle_size(),
            'min_size': self.config.min_pool_size,
            'max_size': self.config.max_pool_size
        }
    
    async def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get information about a table
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table information
        """
        # Get columns
        columns_query = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
        """
        columns = await self.fetch(columns_query, table_name)
        
        # Get row count
        count = await self.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
        
        # Get indexes
        indexes_query = """
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = $1
        """
        indexes = await self.fetch(indexes_query, table_name)
        
        return {
            'table_name': table_name,
            'columns': [dict(col) for col in columns],
            'row_count': count,
            'indexes': [dict(idx) for idx in indexes]
        }
    
    async def get_all_tables(self) -> List[str]:
        """
        Get list of all tables in the database
        
        Returns:
            List of table names
        """
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        result = await self.fetch(query)
        return [row['table_name'] for row in result]
    
    async def refresh_materialized_views(self):
        """Refresh all materialized views"""
        logger.info("Refreshing materialized views...")
        await self.execute("SELECT refresh_all_materialized_views()")
        logger.info("✅ Materialized views refreshed")


class DatabaseMigration:
    """
    Handle database schema migrations
    """
    
    def __init__(self, db: DatabaseConnection):
        self.db = db
    
    async def apply_schema(self, schema_file: str):
        """
        Apply database schema from SQL file
        Executes the entire schema file in a single transaction
        
        Args:
            schema_file: Path to schema.sql file
        """
        logger.info(f"Applying schema from {schema_file}...")
        
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        try:
            # Execute entire schema file using pool connection directly
            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(schema_sql)
            logger.info("✅ Schema applied successfully")
        except Exception as e:
            logger.error(f"❌ Failed to apply schema: {e}")
            raise
    
    async def check_schema_exists(self) -> bool:
        """Check if database schema is initialized"""
        # Check if ANY tables exist (more reliable than checking for specific tables)
        tables = await self.db.get_all_tables()
        return len(tables) > 0
    
    async def initialize_database(self, schema_file: str):
        """
        Initialize database with schema
        
        Args:
            schema_file: Path to schema.sql file
        """
        if await self.check_schema_exists():
            logger.warning("⚠️  Database schema already exists. Skipping initialization.")
            return
        
        logger.info("Initializing database...")
        await self.apply_schema(schema_file)
        logger.info("✅ Database initialized successfully")


# Singleton instance
_db_instance: Optional[DatabaseConnection] = None


def get_database(config: Optional[DatabaseConfig] = None) -> DatabaseConnection:
    """
    Get or create database connection instance
    
    Args:
        config: Database configuration (uses environment if not provided)
        
    Returns:
        DatabaseConnection instance
    """
    global _db_instance
    
    if _db_instance is None:
        if config is None:
            config = DatabaseConfig.from_environment()
        _db_instance = DatabaseConnection(config)
    
    return _db_instance


async def init_database(config: Optional[DatabaseConfig] = None):
    """
    Initialize database connection
    
    Args:
        config: Database configuration (uses environment if not provided)
    """
    db = get_database(config)
    await db.connect()
    return db


async def close_database():
    """Close database connection"""
    global _db_instance
    
    if _db_instance is not None:
        await _db_instance.disconnect()
        _db_instance = None
