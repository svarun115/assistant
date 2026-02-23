#!/usr/bin/env python3
"""
SQL dump (pg_dump) of the journal database.

Creates a compressed .sql.gz file in the default backup directory:
  Windows: %LOCALAPPDATA%\JournalMCP\backups\data\
  Linux:   ~/.local/share/journal-mcp/backups/data/

Usage:
  APP_ENV=production python dump_sql.py
  APP_ENV=production python dump_sql.py my-pre-migration-checkpoint
"""

import sys
from config import load_app_environment, get_backup_root

load_app_environment()

from backup.backup_sql import backup_database

backup_name = sys.argv[1] if len(sys.argv) > 1 else None
output_file = backup_database(backup_name=backup_name)
print(f"SQL dump written to: {output_file}")
