# Backup Utilities# Database Backups# Backups Folder



Backup and restore utilities for the database.



## FilesThis folder contains database backup and recovery utilities, now exposed as MCP tools for clients.This folder contains all database backup and recovery tools.



- `backup_utils.py` - Main implementation with CLI

- `.gitignore` - Prevents backup files in git

- `data/` - Default backup storage location## MCP Tools (For Clients)## Contents



## Usage



See `mcp/resources/BACKUP_TOOLS.md` for MCP tool documentation.Three MCP tools are exposed to allow clients to manage backups:- **`backup_utils.py`** - Main backup/restore script



For CLI usage:- **`BACKUP_GUIDE.md`** - Complete usage guide

```bash

python backup_utils.py backup              # Create backup### 1. `create_database_backup`- **`data/`** - Backup files are stored here automatically

python backup_utils.py list                # List backups

python backup_utils.py restore <file>      # Restore backupCreate a compressed backup of the entire database.- **`README.md`** - This file

```



With custom paths:

```bash**Optional Parameters:**## Quick Start

python backup_utils.py backup --backup-dir /custom/path

python backup_utils.py list --backup-dir /custom/path- `backup_dir` (string) - Custom directory to store backup. Defaults to `backup/data/`

python backup_utils.py restore <file> --target-db other_db

``````bash



## Integration**Examples:**# Create a backup



`init_db.py` automatically creates a backup before database resets.python backup_utils.py backup


Default location:

```json# View backups

{ls -lh data/

  "tool": "create_database_backup"

}# Restore a backup

```python backup_utils.py restore data/backup_assistant_db_test_YYYYMMDD_HHMMSS.sql.gz

```

Custom location:

```json## Important Files

{

  "tool": "create_database_backup",### backup_utils.py

  "arguments": {

    "backup_dir": "/external/backup/path"Main script for backup and restore operations.

  }

}**Usage:**

``````bash

python backup_utils.py backup                    # Create backup

**Returns:** Path to created backup filepython backup_utils.py restore <file>            # Restore backup

```

---

### BACKUP_GUIDE.md

### 2. `restore_database_backup`

Restore the database from a backup file. **Requires explicit "RESTORE" confirmation.**Complete guide with:

- Detailed process explanation

**Parameters:**- Setup instructions

- `backup_file` (string, required) - Path to backup file- Disaster recovery procedures

- `target_db` (string, optional) - Target database name (if restoring to different database)- Troubleshooting tips



**Examples:**Read this for comprehensive information.



Restore to original database:## Folder Structure

```json

{```

  "tool": "restore_database_backup",backups/

  "arguments": {├── backup_utils.py

    "backup_file": "backup/data/backup_assistant_db_20251105_182000.sql.gz"├── BACKUP_GUIDE.md

  }├── README.md

}└── data/                          ← Backup files go here

```    ├── backup_assistant_db_test_20251105_182000.sql.gz

    ├── backup_assistant_db_test_20251104_200000.sql.gz

Restore to different database:    └── ...

```json```

{

  "tool": "restore_database_backup",## Key Points

  "arguments": {

    "backup_file": "backup/data/backup_assistant_db_20251105_182000.sql.gz",- Backups are automatically created in `data/` subfolder

    "target_db": "test_db"- Backups are compressed (`.sql.gz`) to save space

  }- Last 7 backups are kept automatically

}- Old backups are automatically deleted

```- Each backup is timestamped: `backup_<database>_<YYYYMMDD_HHMMSS>.sql.gz`



**Note:** The target database must already exist.## Integration with init_db.py



---When you run:

```bash

### 3. `list_database_backups`python ../init_db.py reset -f

List all available backups with their sizes and creation times.```



**Optional Parameters:**It automatically:

- `backup_dir` (string) - Custom directory to list backups from. Defaults to `backup/data/`1. Creates a backup in `backups/data/`

2. Resets the database

**Examples:**3. Reloads schema



Default location:So your data is always backed up before any destructive operation.

```json

{## See Also

  "tool": "list_database_backups"

}- `BACKUP_GUIDE.md` - Detailed usage instructions

```- `../BACKUP_GUIDE.md` - Also in project root for quick reference


Custom location:
```json
{
  "tool": "list_database_backups",
  "arguments": {
    "backup_dir": "/external/backup/path"
  }
}
```

---

## Command Line Usage

For direct CLI usage (not via MCP):

```bash
# Create a backup (default location: backup/data/)
python backup_utils.py backup

# Create a backup to custom location
python backup_utils.py backup --backup-dir /path/to/backups

# List all backups
python backup_utils.py list

# List backups from custom location
python backup_utils.py list --backup-dir /path/to/backups

# Restore a backup
python backup_utils.py restore backup/data/backup_assistant_db_20251105_182000.sql.gz

# Restore to different database
python backup_utils.py restore backup/data/backup_assistant_db_20251105_182000.sql.gz --target-db new_db
```

## Folder Structure

```
backup/
├── backup_utils.py                ← Main utilities (with CLI)
├── BACKUP_GUIDE.md                ← Detailed documentation
├── README.md                       ← This file
├── .gitignore                      ← Prevents backups in git
└── data/                           ← Default backup location
    ├── backup_assistant_db_20251105_182000.sql.gz
    ├── backup_assistant_db_20251104_200000.sql.gz
    └── ...
```

## Key Features

✅ **Configurable backup location** - Clients specify any directory via `backup_dir` parameter  
✅ **Compressed backups** - Automatic gzip compression (~10-20x size reduction)  
✅ **Automatic cleanup** - Keeps only last 7 backups in default location  
✅ **Cross-database restore** - Restore backup to a different database  
✅ **Timestamped files** - Format: `backup_<database>_<YYYYMMDD_HHMMSS>.sql.gz`  
✅ **Complete data** - Backs up everything: schemas, data, indexes, triggers  
✅ **Safety confirmations** - Restore requires explicit "RESTORE" confirmation  

## Integration with init_db.py

The `init_db.py` script automatically creates a backup before any database reset:

```bash
python ../init_db.py reset -f
```

This will:
1. Create automatic backup in `backup/data/`
2. Reset the database
3. Reload schema

Your data is always protected before destructive operations.

## Backup File Examples

```
backup_assistant_db_20251105_182000.sql.gz    # Database: assistant_db, Date: 2025-11-05, Time: 18:20:00
backup_test_db_20251105_143022.sql.gz         # Database: test_db, Date: 2025-11-05, Time: 14:30:22
```

## Common Scenarios

### Scenario 1: Regular Backup to Custom Location

```json
{
  "tool": "create_database_backup",
  "arguments": {
    "backup_dir": "/mnt/nfs/daily_backups"
  }
}
```

### Scenario 2: Test Restore to Separate Database

```json
{
  "tool": "list_database_backups"
}
```

Then restore to test database:
```json
{
  "tool": "restore_database_backup",
  "arguments": {
    "backup_file": "backup/data/backup_assistant_db_20251105_182000.sql.gz",
    "target_db": "test_db"
  }
}
```

### Scenario 3: Disaster Recovery

```json
{
  "tool": "list_database_backups"
}
```

View backups and restore most recent:
```json
{
  "tool": "restore_database_backup",
  "arguments": {
    "backup_file": "backup/data/backup_assistant_db_20251105_182000.sql.gz"
  }
}
```

## See Also

- `BACKUP_GUIDE.md` - Comprehensive guide with setup and troubleshooting
- `backup_utils.py` - Source code and CLI implementation
- `../init_db.py` - Auto-backup integration in database initialization
