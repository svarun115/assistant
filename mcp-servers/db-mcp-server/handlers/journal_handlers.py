import logging
from datetime import date
from typing import List, Dict, Any

from mcp import types
from container import RepositoryContainer
from models import JournalEntryCreate

logger = logging.getLogger(__name__)

async def handle_log_journal_entry(arguments: dict, repos: RepositoryContainer) -> list[types.TextContent]:
    """
    Log a raw journal entry to memory.
    """
    text = arguments.get("text")
    entry_type = arguments.get("entry_type", "journal")
    tags = arguments.get("tags", [])
    entry_date_str = arguments.get("entry_date")
    
    if not text:
        raise ValueError("Text content is required")
        
    try:
        # Ensure entry_date is a string (YYYY-MM-DD)
        if entry_date_str:
            entry_date = entry_date_str
        else:
            entry_date = date.today().isoformat()
            
        entry_data = JournalEntryCreate(
            raw_text=text,
            entry_date=entry_date,
            entry_type=entry_type,
            tags=tags
        )
        
        entry = await repos.memory.log_entry(entry_data)
        
        return [types.TextContent(
            type="text",
            text=f"Successfully logged entry {entry.id} for {entry.entry_date}"
        )]
        
    except Exception as e:
        logger.error(f"Error logging journal entry: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error logging entry: {str(e)}"
        )]

async def handle_search_journal_history(arguments: dict, repos: RepositoryContainer) -> list[types.TextContent]:
    """
    Semantically search journal history with optional filtering.
    """
    query = arguments.get("query")
    limit = arguments.get("limit", 5)
    start_date_str = arguments.get("start_date")
    end_date_str = arguments.get("end_date")
    entry_types = arguments.get("entry_types")
    tags = arguments.get("tags")
    
    if not query:
        raise ValueError("Query is required")
        
    try:
        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None
        
        results = await repos.memory.search_history(
            query=query,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            entry_types=entry_types,
            tags=tags
        )
        
        if not results:
            return [types.TextContent(
                type="text",
                text="No matching entries found."
            )]
            
        output = ["Found the following relevant entries:\n"]
        for r in results:
            meta = r['metadata']
            entry_tags = meta.get('tags', '')
            output.append(f"--- Date: {meta.get('date')} (Type: {meta.get('type')}) ---")
            if entry_tags:
                output.append(f"Tags: {entry_tags}")
            output.append(f"{r['text']}")
            output.append("")
            
        return [types.TextContent(
            type="text",
            text="\n".join(output)
        )]
        
    except Exception as e:
        logger.error(f"Error searching journal: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error searching journal: {str(e)}"
        )]

async def handle_delete_journal_entry(arguments: dict, repos: RepositoryContainer) -> list[types.TextContent]:
    """
    Soft delete a journal entry.
    """
    from uuid import UUID
    
    entry_id = arguments.get("entry_id")
    if not entry_id:
        raise ValueError("entry_id is required")
        
    try:
        entry_uuid = UUID(entry_id)
        result = await repos.journal.delete_entry(entry_uuid)
        
        # Also remove from vector store if enabled
        if repos.memory.config.enabled and repos.memory.collection:
            try:
                repos.memory.collection.delete(ids=[str(entry_uuid)])
                logger.info(f"Removed entry {entry_uuid} from vector store")
            except Exception as e:
                logger.warning(f"Failed to remove from vector store: {e}")
        
        return [types.TextContent(
            type="text",
            text=f"Successfully deleted journal entry {entry_id}"
        )]
        
    except ValueError as e:
        logger.error(f"Error deleting journal entry: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]
    except Exception as e:
        logger.error(f"Unexpected error deleting journal entry: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error deleting entry: {str(e)}"
        )]

async def handle_undelete_journal_entry(arguments: dict, repos: RepositoryContainer) -> list[types.TextContent]:
    """
    Restore a soft-deleted journal entry.
    """
    from uuid import UUID
    
    entry_id = arguments.get("entry_id")
    if not entry_id:
        raise ValueError("entry_id is required")
        
    try:
        entry_uuid = UUID(entry_id)
        result = await repos.journal.undelete_entry(entry_uuid)
        
        # Re-index in vector store if enabled
        if repos.memory.config.enabled and repos.memory.collection:
            try:
                entry = await repos.journal.get_by_id(entry_uuid)
                if entry:
                    embedding = repos.memory._generate_embedding(entry.raw_text)
                    date_int = entry.entry_date.year * 10000 + entry.entry_date.month * 100 + entry.entry_date.day
                    metadata = {
                        "date": str(entry.entry_date),
                        "date_int": date_int,
                        "type": entry.entry_type,
                        "tags": ",".join(entry.tags) if entry.tags else ""
                    }
                    repos.memory.collection.add(
                        ids=[str(entry_uuid)],
                        documents=[entry.raw_text],
                        embeddings=[embedding],
                        metadatas=[metadata]
                    )
                    logger.info(f"Re-indexed entry {entry_uuid} in vector store")
            except Exception as e:
                logger.warning(f"Failed to re-index in vector store: {e}")
        
        return [types.TextContent(
            type="text",
            text=f"Successfully restored journal entry {entry_id}"
        )]
        
    except ValueError as e:
        logger.error(f"Error restoring journal entry: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]
    except Exception as e:
        logger.error(f"Unexpected error restoring journal entry: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error restoring entry: {str(e)}"
        )]

async def handle_get_journal_by_date(arguments: dict, repos: RepositoryContainer) -> list[types.TextContent]:
    """
    Get all entries for a specific date.
    """
    entry_date_str = arguments.get("entry_date")
    
    if not entry_date_str:
        raise ValueError("entry_date is required")
        
    try:
        entry_date = date.fromisoformat(entry_date_str)
        entries = await repos.memory.get_entries_by_date(entry_date)
        
        if not entries:
            return [types.TextContent(
                type="text",
                text=f"No entries found for {entry_date_str}"
            )]
            
        output = [f"Journal Entries for {entry_date_str}:\n"]
        for entry in entries:
            output.append(f"[{entry.created_at.strftime('%H:%M')}] ({entry.entry_type})")
            output.append(entry.raw_text)
            output.append("")
            
        return [types.TextContent(
            type="text",
            text="\n".join(output)
        )]
        
    except Exception as e:
        logger.error(f"Error retrieving journal: {e}")
        return [types.TextContent(
            type="text",
            text=f"Error retrieving journal: {str(e)}"
        )]
