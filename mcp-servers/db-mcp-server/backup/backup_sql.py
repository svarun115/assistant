"""
SQL Backup Utility
Creates PostgreSQL dumps using pg_dump.
"""

import subprocess
import gzip
import logging
import os
import shutil
import json
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from config import DatabaseConfig, get_backup_root

logger = logging.getLogger(__name__)


def find_pg_dump() -> Optional[str]:
    """
    Find pg_dump executable, checking PATH first, then common PostgreSQL installation directories.
    
    Returns:
        Path to pg_dump executable if found, None otherwise
    """
    # Check if pg_dump is in PATH
    pg_dump = shutil.which("pg_dump")
    if pg_dump:
        return pg_dump
    
    # On Windows, check common PostgreSQL installation directories
    if os.name == 'nt':  # Windows
        # Check for PostgreSQL installations in Program Files
        program_files = os.environ.get('ProgramFiles', 'C:\\Program Files')
        postgres_base = Path(program_files) / 'PostgreSQL'
        
        if postgres_base.exists():
            # Sort versions in descending order (newest first)
            versions = sorted(
                [d for d in postgres_base.iterdir() if d.is_dir()],
                key=lambda x: x.name,
                reverse=True
            )
            
            for version_dir in versions:
                pg_dump_path = version_dir / 'bin' / 'pg_dump.exe'
                if pg_dump_path.exists():
                    logger.info(f"Found pg_dump at {pg_dump_path}")
                    return str(pg_dump_path)
    
    # On Unix-like systems, check common locations
    else:
        common_paths = [
            '/usr/bin/pg_dump',
            '/usr/local/bin/pg_dump',
            '/opt/homebrew/bin/pg_dump',  # macOS Homebrew ARM
            '/usr/local/opt/postgresql/bin/pg_dump',  # macOS Homebrew Intel
        ]
        
        for path in common_paths:
            if Path(path).exists():
                logger.info(f"Found pg_dump at {path}")
                return path
    
    return None


def find_psql() -> Optional[str]:
    """
    Find psql executable, checking PATH first, then common PostgreSQL installation directories.
    
    Returns:
        Path to psql executable if found, None otherwise
    """
    # Check if psql is in PATH
    psql = shutil.which("psql")
    if psql:
        return psql
    
    # On Windows, check common PostgreSQL installation directories
    if os.name == 'nt':  # Windows
        # Check for PostgreSQL installations in Program Files
        program_files = os.environ.get('ProgramFiles', 'C:\\Program Files')
        postgres_base = Path(program_files) / 'PostgreSQL'
        
        if postgres_base.exists():
            # Sort versions in descending order (newest first)
            versions = sorted(
                [d for d in postgres_base.iterdir() if d.is_dir()],
                key=lambda x: x.name,
                reverse=True
            )
            
            for version_dir in versions:
                psql_path = version_dir / 'bin' / 'psql.exe'
                if psql_path.exists():
                    logger.info(f"Found psql at {psql_path}")
                    return str(psql_path)
    
    # On Unix-like systems, check common locations
    else:
        common_paths = [
            '/usr/bin/psql',
            '/usr/local/bin/psql',
            '/opt/homebrew/bin/psql',  # macOS Homebrew ARM
            '/usr/local/opt/postgresql/bin/psql',  # macOS Homebrew Intel
        ]
        
        for path in common_paths:
            if Path(path).exists():
                logger.info(f"Found psql at {path}")
                return path
    
    return None


def generate_metadata(config: DatabaseConfig) -> Dict[str, Any]:
    """Generate metadata (row counts) for the database."""
    try:
        conn = psycopg2.connect(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password
        )
        cur = conn.cursor()
        
        counts = {}
        tables = [
            'events', 'people', 'locations', 'workouts', 'meals', 
            'journal_entries', 'journal_days', 'exercises'
        ]
        
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
            except Exception:
                counts[table] = -1  # Table might not exist
                conn.rollback()
                
        cur.close()
        conn.close()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "database": config.database,
            "type": "sql_dump",
            "counts": counts
        }
    except Exception as e:
        logger.warning(f"Failed to generate metadata: {e}")
        return {"error": str(e)}


def backup_database(backup_dir: str = None, backup_name: str = None) -> Path:
    """
    Create a PostgreSQL backup dump
    
    Args:
        backup_dir: Directory to store backups. If None, uses default "backup/data"
        backup_name: Optional name for the backup file. If None, uses timestamp.
        
    Returns:
        Path to backup file
    """
    if backup_dir is None:
        backup_dir = get_backup_root() / "data"
    config = DatabaseConfig.from_environment()
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    
    if backup_name:
        if not backup_name.endswith('.sql'):
            backup_name += '.sql'
        backup_file = backup_path / backup_name
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"backup_{config.database}_{timestamp}.sql"
    
    try:
        # Find pg_dump and psql executables
        pg_dump = find_pg_dump()
        if pg_dump is None:
            logger.warning("⚠️  pg_dump not found in PATH or common PostgreSQL installation directories")
            raise FileNotFoundError("pg_dump not available - cannot create backup")
        
        psql = find_psql()
        if psql is None:
            logger.warning("⚠️  psql not found in PATH or common PostgreSQL installation directories")
            raise FileNotFoundError("psql not available - cannot verify database")
        
        # Set up environment with password and disable SSL mode
        env = os.environ.copy()
        env["PGSSLMODE"] = "disable"  # Disable SSL to avoid encryption key errors

        # Only set PGPASSWORD if a password is configured
        if config.password:
            env["PGPASSWORD"] = config.password
        
        # On Windows, localhost may not resolve - use 127.0.0.1 instead
        host = config.host
        if host == "localhost" and os.name == 'nt':
            host = "127.0.0.1"
            logger.info("Using 127.0.0.1 instead of localhost on Windows")
        
        # First, verify the database exists
        logger.info(f"Verifying database '{config.database}' exists...")
        check_result = subprocess.run(
            [
                psql,
                "-h", host,
                "-p", str(config.port),
                "-U", config.user,
                "-d", "postgres",  # Connect to postgres database to check if target db exists
                "-t",  # Tuples only
                "-c", f"SELECT 1 FROM pg_database WHERE datname = '{config.database}'"
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )
        
        if check_result.returncode != 0:
            raise Exception(f"Failed to connect to PostgreSQL: {check_result.stderr}")
        
        check_stdout = check_result.stdout or ""
        if not check_stdout.strip():
            raise Exception(
                f"Database '{config.database}' does not exist. "
                f"Please check your DB_NAME environment variable or create the database first."
            )
        
        logger.info(f"[OK] Database '{config.database}' exists, proceeding with backup...")
        
        # Run pg_dump with additional options to avoid common Windows errors.
        # Use -f to write directly to a file (more robust than capturing stdout).
        result = subprocess.run(
            [
                pg_dump,
                "-h", host,
                "-p", str(config.port),
                "-U", config.user,
                "-F", "plain",
                "-f", str(backup_file),
                "--no-tablespaces",  # Avoid tablespace permission errors
                "--no-owner",  # Don't set ownership in dump
                "--no-privileges",  # Don't dump privileges (GRANT/REVOKE)
                config.database
            ],
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )
        
        if result.returncode != 0:
            # Provide helpful error messages for common issues
            error_msg = result.stderr
            if "could not generate restrict key" in error_msg:
                raise Exception(
                    f"pg_dump failed with cryptographic error. This may be due to:\n"
                    f"1. PostgreSQL version mismatch (pg_dump vs server)\n"
                    f"2. Authentication configuration (try md5 instead of scram-sha-256)\n"
                    f"3. Missing system libraries\n"
                    f"Original error: {error_msg}"
                )
            else:
                raise Exception(f"pg_dump failed: {error_msg}")
        
        # Validate that the dump file was created and is non-empty.
        if not backup_file.exists():
            raise Exception(
                "pg_dump reported success but no output file was created. "
                f"Expected: {backup_file}. stderr: {result.stderr}"
            )
        if backup_file.stat().st_size == 0:
            raise Exception(
                "pg_dump created an empty dump file. "
                f"File: {backup_file}. stderr: {result.stderr}"
            )

        logger.info(f"[OK] Backup created: {backup_file}")
        
        # Generate and save metadata
        try:
            metadata = generate_metadata(config)
            meta_file = Path(str(backup_file) + ".meta.json")
            with open(meta_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"[OK] Metadata saved: {meta_file}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save metadata: {e}")
        
        # Compress
        backup_file_gz = Path(str(backup_file) + ".gz")
        with open(backup_file, 'rb') as f_in:
            with gzip.open(backup_file_gz, 'wb') as f_out:
                f_out.writelines(f_in)
        
        backup_file.unlink()  # Remove uncompressed version
        logger.info(f"[OK] Compressed: {backup_file_gz}")
        
        # Cleanup old backups (keep only newest 7 by modification time)
        all_backups = sorted(backup_path.glob(f"backup_{config.database}_*.sql.gz"), key=lambda f: f.stat().st_mtime)
        for old_backup in all_backups[:-7]:
            old_backup.unlink()
            logger.info(f"Cleaned up old backup: {old_backup}")
        
        return backup_file_gz
        
    except Exception as e:
        logger.error(f"[ERROR] Backup failed: {e}")
        raise


def list_backups(backup_dir: str = None) -> list[dict]:
    """
    List all available backups in a directory.
    Filters backups to only show those matching the current database name.
    
    Args:
        backup_dir: Directory containing backups. If None, uses default "backup/data"
        
    Returns:
        List of dicts with keys: name, path, size_mb, created (ISO format)
    """
    if backup_dir is None:
        backup_dir = "backup/data"
    
    backup_path = Path(backup_dir)
    
    if not backup_path.exists():
        return []
    
    # Get current database name for filtering
    config = DatabaseConfig.from_environment()
    current_db = config.database
    
    backups = []
    # Filter for backups starting with backup_{current_db}_
    pattern = f"backup_{current_db}_*.sql.gz"
    
    for backup_file in sorted(backup_path.glob(pattern), reverse=True):
        try:
            size_mb = backup_file.stat().st_size / (1024 * 1024)
            created = datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            
            backups.append({
                "name": backup_file.name,
                "path": str(backup_file),
                "size_mb": size_mb,
                "created": created
            })
        except Exception as e:
            logger.warning(f"Failed to get info for {backup_file}: {e}")
    
    return backups


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Usage: python backup_sql.py [backup|list] [backup_name] [--backup-dir DIR]")
        print("\nExamples:")
        print("  python backup_sql.py backup")
        print("  python backup_sql.py backup --backup-dir /path/to/backups")
        print("  python backup_sql.py list")
        print("  python backup_sql.py list --backup-dir /path/to/backups")
        sys.exit(1)
    
    command = sys.argv[1]
    
    # Parse --backup-dir option
    backup_dir_arg = None
    if "--backup-dir" in sys.argv:
        idx = sys.argv.index("--backup-dir")
        if idx + 1 < len(sys.argv):
            backup_dir_arg = sys.argv[idx + 1]
    
    if command == "backup":
        backup_database(backup_dir=backup_dir_arg)
    elif command == "list":
        backups = list_backups(backup_dir_arg)
        if not backups:
            print("No backups found.")
        else:
            print(f"Found {len(backups)} backups:\n")
            for i, backup in enumerate(backups, 1):
                print(f"{i}. {backup['name']}")
                print(f"   Size: {backup['size_mb']:.2f} MB")
                print(f"   Created: {backup['created']}\n")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
