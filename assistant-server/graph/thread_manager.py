"""
Thread Manager - Thread listing, search, and metadata on top of LangGraph checkpointer.

LangGraph's checkpointer persists state per thread_id, but doesn't provide:
- Thread listing (get all threads)
- Thread search (by title, date, content)
- Thread metadata (title, created_at, last_updated, message_count)
- Thread deletion

This module adds a SQLite table for thread metadata that syncs with the checkpointer.
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ThreadMetadata:
    """Metadata for a conversation thread."""
    thread_id: str
    title: str
    created_at: str  # ISO format
    last_updated: str  # ISO format
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    mode: str  # Last known session mode
    target_date: Optional[str]  # Last known target date
    model_provider: Optional[str] = None  # e.g., 'claude', 'openai', 'mock'
    model_name: Optional[str] = None  # e.g., 'claude-sonnet-4-20250514'
    is_deleted: bool = False
    emoji: Optional[str] = None  # Thread emoji icon
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_row(cls, row: tuple) -> "ThreadMetadata":
        # Row columns: thread_id, title, created_at, last_updated, message_count,
        #              total_input_tokens, total_output_tokens, mode, target_date,
        #              model_provider, model_name, is_deleted, emoji
        # Indices:     0          1      2           3             4
        #              5                  6                        7     8
        #              9               10          11          12
        return cls(
            thread_id=row[0],
            title=row[1],
            created_at=row[2],
            last_updated=row[3],
            message_count=row[4],
            total_input_tokens=row[5],
            total_output_tokens=row[6],
            mode=row[7],
            target_date=row[8],
            model_provider=row[9] if len(row) > 9 else None,
            model_name=row[10] if len(row) > 10 else None,
            is_deleted=bool(row[11]) if len(row) > 11 else False,
            emoji=row[12] if len(row) > 12 else None,
        )


class ThreadManager:
    """
    Manages thread metadata separately from LangGraph checkpointer.
    
    This provides the thread listing, search, and metadata functionality
    that the base checkpointer doesn't have.
    
    Usage:
        manager = ThreadManager("journal_threads_meta.db")
        
        # Create new thread
        thread_id = manager.create_thread("Journal for Dec 31")
        
        # List threads
        threads = manager.list_threads(limit=20)
        
        # Update metadata after graph run
        manager.sync_from_state(thread_id, state)
        
        # Search
        results = manager.search_threads("December")
    """
    
    def __init__(self, db_path: str = "journal_threads_meta.db"):
        """
        Initialize thread manager.
        
        Args:
            db_path: Path to SQLite database for thread metadata.
                    This is separate from the LangGraph checkpointer database.
        """
        self.db_path = db_path
        # Track how many usage_records have been persisted per thread
        # This survives across sync_from_state calls within the same session
        self._persisted_usage_counts: dict[str, int] = {}
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS thread_metadata (
                    thread_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    total_input_tokens INTEGER DEFAULT 0,
                    total_output_tokens INTEGER DEFAULT 0,
                    mode TEXT DEFAULT 'idle',
                    target_date TEXT,
                    model_provider TEXT,
                    model_name TEXT,
                    is_deleted INTEGER DEFAULT 0
                )
            """)
            
            # Usage ledger: append-only table for token/cost tracking
            # This persists even when threads are deleted
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    model_provider TEXT,
                    model_name TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Index for time-range queries on usage_ledger
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_ledger_timestamp
                ON usage_ledger(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_ledger_model
                ON usage_ledger(model_name, timestamp)
            """)
            
            # Migration: Add model columns to existing tables
            try:
                conn.execute("ALTER TABLE thread_metadata ADD COLUMN model_provider TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE thread_metadata ADD COLUMN model_name TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE thread_metadata ADD COLUMN emoji TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Index for listing and search
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_thread_updated 
                ON thread_metadata(is_deleted, last_updated DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_thread_title 
                ON thread_metadata(title)
            """)
            
            # Migration: Backfill usage_ledger from existing thread_metadata
            # This runs once - only migrates threads that don't have ledger entries
            cursor = conn.execute("""
                SELECT COUNT(*) FROM usage_ledger
            """)
            ledger_count = cursor.fetchone()[0]
            
            if ledger_count == 0:
                # Ledger is empty, migrate from thread_metadata
                cursor = conn.execute("""
                    SELECT thread_id, created_at, model_provider, model_name,
                           total_input_tokens, total_output_tokens
                    FROM thread_metadata
                    WHERE total_input_tokens > 0 OR total_output_tokens > 0
                """)
                rows = cursor.fetchall()
                
                for row in rows:
                    thread_id, created_at, model_provider, model_name, input_tokens, output_tokens = row
                    conn.execute("""
                        INSERT INTO usage_ledger 
                        (timestamp, thread_id, model_provider, model_name, input_tokens, output_tokens)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (created_at, thread_id, model_provider, model_name, input_tokens, output_tokens))
                
                if rows:
                    logger.info(f"Migrated {len(rows)} threads to usage_ledger")
            
            conn.commit()
            logger.info(f"Thread metadata database initialized: {self.db_path}")
        finally:
            conn.close()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    # -------------------------------------------------------------------------
    # Thread CRUD
    # -------------------------------------------------------------------------
    
    def create_thread(
        self, 
        title: str = "New Conversation",
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> str:
        """
        Create a new thread and return its ID.
        
        Args:
            title: Display title for the thread
            model_provider: LLM provider (e.g., 'claude', 'openai', 'mock')
            model_name: Model identifier (e.g., 'claude-sonnet-4-20250514')
        
        Returns:
            Generated thread_id (UUID format)
        """
        import uuid
        thread_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO thread_metadata 
                (thread_id, title, created_at, last_updated, message_count,
                 total_input_tokens, total_output_tokens, mode, target_date,
                 model_provider, model_name, is_deleted)
                VALUES (?, ?, ?, ?, 0, 0, 0, 'idle', NULL, ?, ?, 0)
            """, (thread_id, title, now, now, model_provider, model_name))
            conn.commit()
            logger.info(f"Created thread: {thread_id} - {title} (model: {model_provider}/{model_name})")
        finally:
            conn.close()
        
        return thread_id
    
    def get_thread(self, thread_id: str) -> Optional[ThreadMetadata]:
        """Get metadata for a specific thread."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT thread_id, title, created_at, last_updated, message_count,
                       total_input_tokens, total_output_tokens, mode, target_date,
                       model_provider, model_name, is_deleted, emoji
                FROM thread_metadata
                WHERE thread_id = ?
            """, (thread_id,))
            row = cursor.fetchone()
            if row:
                return ThreadMetadata.from_row(row)
            return None
        finally:
            conn.close()
    
    def update_thread(
        self,
        thread_id: str,
        title: Optional[str] = None,
        message_count: Optional[int] = None,
        total_input_tokens: Optional[int] = None,
        total_output_tokens: Optional[int] = None,
        mode: Optional[str] = None,
        target_date: Optional[str] = None,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        emoji: Optional[str] = None,
    ) -> bool:
        """
        Update thread metadata.
        
        Only non-None values are updated.
        """
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if message_count is not None:
            updates.append("message_count = ?")
            params.append(message_count)
        if total_input_tokens is not None:
            updates.append("total_input_tokens = ?")
            params.append(total_input_tokens)
        if total_output_tokens is not None:
            updates.append("total_output_tokens = ?")
            params.append(total_output_tokens)
        if mode is not None:
            updates.append("mode = ?")
            params.append(mode)
        if target_date is not None:
            updates.append("target_date = ?")
            params.append(target_date)
        if model_provider is not None:
            updates.append("model_provider = ?")
            params.append(model_provider)
        if model_name is not None:
            updates.append("model_name = ?")
            params.append(model_name)
        if emoji is not None:
            updates.append("emoji = ?")
            params.append(emoji)
        
        if not updates:
            return True
        
        # Always update last_updated
        updates.append("last_updated = ?")
        params.append(datetime.now().isoformat())
        
        params.append(thread_id)
        
        conn = self._get_conn()
        try:
            conn.execute(f"""
                UPDATE thread_metadata
                SET {', '.join(updates)}
                WHERE thread_id = ?
            """, params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update thread {thread_id}: {e}")
            return False
        finally:
            conn.close()
    
    def delete_thread(self, thread_id: str) -> bool:
        """Soft delete a thread."""
        conn = self._get_conn()
        try:
            conn.execute("""
                UPDATE thread_metadata
                SET is_deleted = 1, last_updated = ?
                WHERE thread_id = ?
            """, (datetime.now().isoformat(), thread_id))
            conn.commit()
            logger.info(f"Soft deleted thread: {thread_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            return False
        finally:
            conn.close()
    
    def restore_thread(self, thread_id: str) -> bool:
        """Restore a soft-deleted thread."""
        conn = self._get_conn()
        try:
            conn.execute("""
                UPDATE thread_metadata
                SET is_deleted = 0, last_updated = ?
                WHERE thread_id = ?
            """, (datetime.now().isoformat(), thread_id))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def get_most_recent_thread(self, with_messages_only: bool = True) -> Optional[ThreadMetadata]:
        """
        Get the most recently updated thread.
        
        Args:
            with_messages_only: If True, only return threads that have at least one message.
        
        Returns:
            Most recent ThreadMetadata or None if no threads exist.
        """
        conn = self._get_conn()
        try:
            if with_messages_only:
                cursor = conn.execute("""
                    SELECT thread_id, title, created_at, last_updated, message_count,
                           total_input_tokens, total_output_tokens, mode, target_date,
                           model_provider, model_name, is_deleted, emoji
                    FROM thread_metadata
                    WHERE is_deleted = 0 AND message_count > 0
                    ORDER BY last_updated DESC
                    LIMIT 1
                """)
            else:
                cursor = conn.execute("""
                    SELECT thread_id, title, created_at, last_updated, message_count,
                           total_input_tokens, total_output_tokens, mode, target_date,
                           model_provider, model_name, is_deleted, emoji
                    FROM thread_metadata
                    WHERE is_deleted = 0
                    ORDER BY last_updated DESC
                    LIMIT 1
                """)
            row = cursor.fetchone()
            if row:
                return ThreadMetadata.from_row(row)
            return None
        finally:
            conn.close()
    
    # -------------------------------------------------------------------------
    # Thread Listing
    # -------------------------------------------------------------------------
    
    def list_threads(
        self,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        with_messages_only: bool = True,
    ) -> list[ThreadMetadata]:
        """
        List threads ordered by last_updated descending.
        
        Args:
            limit: Maximum number of threads to return
            offset: Offset for pagination
            include_deleted: Whether to include soft-deleted threads
        
        Returns:
            List of ThreadMetadata objects
        """
        conn = self._get_conn()
        try:
            # Build the WHERE clause based on options
            conditions = []
            if not include_deleted:
                conditions.append("is_deleted = 0")
            if with_messages_only:
                conditions.append("message_count > 0")
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            
            cursor = conn.execute(f"""
                SELECT thread_id, title, created_at, last_updated, message_count,
                       total_input_tokens, total_output_tokens, mode, target_date,
                       model_provider, model_name, is_deleted, emoji
                FROM thread_metadata
                {where_clause}
                ORDER BY last_updated DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            return [ThreadMetadata.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_thread_count(self, include_deleted: bool = False, with_messages_only: bool = True) -> int:
        """Get total number of threads."""
        conn = self._get_conn()
        try:
            conditions = []
            if not include_deleted:
                conditions.append("is_deleted = 0")
            if with_messages_only:
                conditions.append("message_count > 0")
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cursor = conn.execute(f"SELECT COUNT(*) FROM thread_metadata {where_clause}")
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    # -------------------------------------------------------------------------
    # Thread Search
    # -------------------------------------------------------------------------
    
    def search_threads(
        self,
        query: str,
        limit: int = 20,
    ) -> list[ThreadMetadata]:
        """
        Search threads by title.
        
        Args:
            query: Search query (matched against title, case-insensitive)
            limit: Maximum results
        
        Returns:
            Matching threads ordered by relevance (last_updated)
        """
        conn = self._get_conn()
        try:
            # Simple LIKE search for now
            # Could be upgraded to FTS5 for better search
            cursor = conn.execute("""
                SELECT thread_id, title, created_at, last_updated, message_count,
                       total_input_tokens, total_output_tokens, mode, target_date,
                       model_provider, model_name, is_deleted, emoji
                FROM thread_metadata
                WHERE is_deleted = 0 AND title LIKE ?
                ORDER BY last_updated DESC
                LIMIT ?
            """, (f"%{query}%", limit))
            
            return [ThreadMetadata.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def search_by_date(
        self,
        target_date: str,
        limit: int = 20,
    ) -> list[ThreadMetadata]:
        """
        Search threads by target date.
        
        Args:
            target_date: Date in YYYY-MM-DD format
            limit: Maximum results
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT thread_id, title, created_at, last_updated, message_count,
                       total_input_tokens, total_output_tokens, mode, target_date,
                       model_provider, model_name, is_deleted, emoji
                FROM thread_metadata
                WHERE is_deleted = 0 AND target_date = ?
                ORDER BY last_updated DESC
                LIMIT ?
            """, (target_date, limit))
            
            return [ThreadMetadata.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    # -------------------------------------------------------------------------
    # State Sync
    # -------------------------------------------------------------------------
    
    def sync_from_state(self, thread_id: str, state: dict) -> None:
        """
        Sync thread metadata from LangGraph state.
        
        Call this after each graph invocation to keep metadata in sync.
        Also records new usage records to the usage ledger.
        
        Args:
            thread_id: Thread ID
            state: LangGraph state dict
        """
        from langchain_core.messages import HumanMessage, AIMessage
        
        # Count messages
        messages = state.get("messages", [])
        message_count = len([m for m in messages if isinstance(m, (HumanMessage, AIMessage))])
        
        # Get title (use thread_title from state if set)
        title = state.get("thread_title", "New Conversation")
        
        # Get usage
        total_input = state.get("total_input_tokens", 0)
        total_output = state.get("total_output_tokens", 0)
        
        # Get session info
        mode = state.get("mode", "idle")
        target_date = state.get("target_date")
        
        # Record new usage records to the ledger
        usage_records = state.get("usage_records", [])
        persisted_count = self._persisted_usage_counts.get(thread_id, 0)
        
        for record in usage_records[persisted_count:]:
            self.record_usage(
                thread_id=thread_id,
                input_tokens=record.get("input_tokens", 0),
                output_tokens=record.get("output_tokens", 0),
                model_provider=record.get("provider"),
                model_name=record.get("model"),
            )
        
        # Update persisted count
        self._persisted_usage_counts[thread_id] = len(usage_records)
        
        # Check if thread exists
        existing = self.get_thread(thread_id)
        if not existing:
            # Create new thread entry
            now = datetime.now().isoformat()
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT INTO thread_metadata 
                    (thread_id, title, created_at, last_updated, message_count,
                     total_input_tokens, total_output_tokens, mode, target_date, is_deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (thread_id, title, now, now, message_count, total_input, total_output, mode, target_date))
                conn.commit()
            finally:
                conn.close()
        else:
            # Update existing - only update title if existing title is "New Conversation"
            # and state has a real title (not the default)
            should_update_title = (
                existing.title == "New Conversation" 
                and title != "New Conversation"
            )
            self.update_thread(
                thread_id,
                title=title if should_update_title else None,
                message_count=message_count,
                total_input_tokens=total_input,
                total_output_tokens=total_output,
                mode=mode,
                target_date=target_date,
            )
    
    # -------------------------------------------------------------------------
    # Usage Ledger
    # -------------------------------------------------------------------------
    
    def record_usage(
        self,
        thread_id: str,
        input_tokens: int,
        output_tokens: int,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """
        Record a usage event to the ledger.
        
        This is an append-only ledger that persists even when threads are deleted.
        Call this whenever tokens are consumed (e.g., after each LLM call).
        """
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO usage_ledger 
                (timestamp, thread_id, model_provider, model_name, input_tokens, output_tokens)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                thread_id,
                model_provider,
                model_name,
                input_tokens,
                output_tokens,
            ))
            conn.commit()
            logger.debug(f"Recorded usage: {input_tokens} in, {output_tokens} out for {model_name}")
        except Exception as e:
            logger.error(f"Failed to record usage: {e}")
        finally:
            conn.close()
    
    # -------------------------------------------------------------------------
    # Usage Aggregation
    # -------------------------------------------------------------------------
    
    def get_thread_usage_by_model(self, thread_id: str, model_name: str) -> dict:
        """Get token usage for a specific thread and model from ledger.
        
        Args:
            thread_id: Thread ID to query
            model_name: Model name to filter by
        
        Returns:
            Dict with input_tokens, output_tokens, call_count
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT 
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    COUNT(*) as call_count
                FROM usage_ledger
                WHERE thread_id = ? AND model_name = ?
            """, (thread_id, model_name))
            row = cursor.fetchone()
            return {
                "input_tokens": row[0] or 0,
                "output_tokens": row[1] or 0,
                "call_count": row[2] or 0,
            }
        finally:
            conn.close()
    
    def get_distillation_usage_by_model(self, model_name: str) -> dict:
        """Get distillation usage for a specific model from ledger.
        
        Queries all distillation usage across all threads for a given model.
        Used for the distillation stats panel.
        
        Args:
            model_name: Distillation model name (e.g., 'gpt-5-nano', 'gpt-4o-mini')
        
        Returns:
            Dict with input_tokens, output_tokens, cost, calls, model
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT 
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    COUNT(*) as call_count
                FROM usage_ledger
                WHERE model_name = ?
            """, (model_name,))
            row = cursor.fetchone()
            
            input_tokens = row[0] or 0
            output_tokens = row[1] or 0
            calls = row[2] or 0
            
            # Calculate cost based on model pricing
            from config import DISTILLATION_MODELS
            pricing = {"input": 0.05, "output": 0.40}  # Default to gpt-5-nano pricing
            for m in DISTILLATION_MODELS:
                if m["model"] == model_name:
                    pricing = m.get("pricing", pricing)
                    break
            
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
            
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "calls": calls,
                "model": model_name
            }
        finally:
            conn.close()
    
    def get_total_usage(self) -> dict:
        """Get total token usage from ledger (includes deleted threads)."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                SELECT 
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    COUNT(*) as entry_count
                FROM usage_ledger
            """)
            row = cursor.fetchone()
            return {
                "total_input_tokens": row[0] or 0,
                "total_output_tokens": row[1] or 0,
                "entry_count": row[2] or 0,
                "total_tokens": (row[0] or 0) + (row[1] or 0),
            }
        finally:
            conn.close()
    
    def get_usage_by_date_range(
        self,
        start_date: str,
        end_date: str,
        model_name: Optional[str] = None,
    ) -> dict:
        """Get token usage from ledger in a date range, optionally filtered by model.
        
        Uses the usage_ledger table which persists even when threads are deleted.
        
        Args:
            start_date: ISO format start date
            end_date: ISO format end date  
            model_name: Optional model name filter (e.g., 'gpt-5-nano')
        
        Returns:
            Dict with usage breakdown by model
        """
        conn = self._get_conn()
        try:
            if model_name:
                # Filter by specific model
                cursor = conn.execute("""
                    SELECT 
                        model_name,
                        SUM(input_tokens) as total_input,
                        SUM(output_tokens) as total_output,
                        COUNT(*) as call_count
                    FROM usage_ledger
                    WHERE timestamp >= ?
                      AND timestamp <= ?
                      AND model_name = ?
                    GROUP BY model_name
                """, (start_date, end_date, model_name))
            else:
                # Get usage breakdown by model
                cursor = conn.execute("""
                    SELECT 
                        model_name,
                        SUM(input_tokens) as total_input,
                        SUM(output_tokens) as total_output,
                        COUNT(*) as call_count
                    FROM usage_ledger
                    WHERE timestamp >= ?
                      AND timestamp <= ?
                    GROUP BY model_name
                """, (start_date, end_date))
            
            rows = cursor.fetchall()
            
            # Build breakdown by model
            by_model = {}
            total_input = 0
            total_output = 0
            total_calls = 0
            
            for row in rows:
                model = row[0] or "unknown"
                input_tokens = row[1] or 0
                output_tokens = row[2] or 0
                calls = row[3] or 0
                
                by_model[model] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "call_count": calls,
                }
                
                total_input += input_tokens
                total_output += output_tokens
                total_calls += calls
            
            return {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "message_count": total_calls,  # Keep this field name for API compatibility
                "total_tokens": total_input + total_output,
                "by_model": by_model,
                "start_date": start_date,
                "end_date": end_date,
            }
        finally:
            conn.close()
