"""
Backup and Restore Tools
Tools for creating and restoring database backups (JSON snapshots and SQL dumps).
"""

from mcp import types

def create_backup_json() -> types.Tool:
    """Create tool definition for create_backup_json"""
    return types.Tool(
        name="create_backup_json",
        description="Create a JSON snapshot backup of the database (portable, human-readable).",
        inputSchema={
            "type": "object",
            "properties": {
                "backup_name": {
                    "type": "string",
                    "description": "Optional name for the backup (defaults to timestamp)"
                }
            }
        }
    )

def request_restore() -> types.Tool:
    """Create tool definition for request_restore"""
    return types.Tool(
        name="request_restore",
        description="Request a database restore from a backup. This logs a request for an administrator to perform the restore manually.",
        inputSchema={
            "type": "object",
            "properties": {
                "backup_name": {
                    "type": "string",
                    "description": "Name of the backup to restore (from list_backups)"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the restore request"
                }
            },
            "required": ["backup_name", "reason"]
        }
    )

def create_backup_sql() -> types.Tool:
    """Create tool definition for create_backup_sql"""
    return types.Tool(
        name="create_backup_sql",
        description="Create a SQL dump backup using pg_dump (complete binary backup).",
        inputSchema={
            "type": "object",
            "properties": {
                "backup_name": {
                    "type": "string",
                    "description": "Optional name for the backup file (defaults to timestamp)"
                }
            }
        }
    )



def list_backups() -> types.Tool:
    """Create tool definition for list_backups"""
    return types.Tool(
        name="list_backups",
        description="List all available database backups (both JSON snapshots and SQL dumps).",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    )

def inspect_backup() -> types.Tool:
    """Create tool definition for inspect_backup"""
    return types.Tool(
        name="inspect_backup",
        description="Get detailed metadata for a specific backup (row counts, date, etc.) to help compare versions.",
        inputSchema={
            "type": "object",
            "properties": {
                "backup_name": {
                    "type": "string",
                    "description": "Name of the backup to inspect (from list_backups)"
                }
            },
            "required": ["backup_name"]
        }
    )
