#!/usr/bin/env python3
"""
JSON snapshot export of the journal database.

Exports all tables as human-readable JSON files in the default backup directory:
  Windows: %LOCALAPPDATA%\JournalMCP\backups\snapshots\
  Linux:   ~/.local/share/journal-mcp/backups/snapshots\

Useful for: inspecting data, migrating to a new server, seeding a dev environment.

Usage:
  APP_ENV=production python dump_json.py
  APP_ENV=production python dump_json.py my-pre-migration-checkpoint
"""

import sys
import os
from datetime import datetime
from config import load_app_environment, get_backup_root, DatabaseConfig

load_app_environment()

from backup.backup_json import backup_database

db_config = DatabaseConfig.from_environment()
db_dict = {
    'host': db_config.host,
    'port': db_config.port,
    'database': db_config.database,
    'user': db_config.user,
    'password': db_config.password,
}

snapshot_name = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d_%H%M%S")
output_dir = get_backup_root() / "snapshots" / f"{db_config.database}_{snapshot_name}"

backup_database(str(output_dir), db_dict)
print(f"JSON snapshot written to: {output_dir}")
