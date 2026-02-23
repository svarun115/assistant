"""
LangGraph-based Journal Agent - Stateful workflow orchestration.

This module provides the LangGraph implementation of the journal agent,
replacing the custom agentic loop with a structured state graph.

Components:
    - state: JournalState TypedDict and related models
    - nodes: Node functions for each step in the workflow
    - graph: Compiled graph builder
    - thread_manager: Thread listing, search, and metadata on top of checkpointer

Usage:
    from graph import create_journal_graph, ThreadManager
    
    # Create graph with default SQLite checkpointer
    graph = create_journal_graph(db_path="journal_graph.db")
    
    # Configure dependencies
    graph.configure(
        mcp_bridge=mcp_bridge,
        llm_client=llm_client,
        skeleton_builder=skeleton_builder,
        skills_loader=skills_loader,
    )
    
    # Create thread manager for listing/search
    thread_manager = ThreadManager("journal_threads_meta.db")
    thread_id = thread_manager.create_thread("My Journal Session")
    
    # Chat
    response = await graph.chat("Log yesterday's workout", thread_id)
    
    # Sync metadata
    state = graph.get_state(thread_id)
    thread_manager.sync_from_state(thread_id, state)
"""

from .state import (
    JournalState,
    SessionMode,
    PendingEntity,
    PartialEvent,
    UsageRecord,
    ToolCallRecord,
    get_initial_state,
    state_to_summary,
)
from .graph import create_journal_graph, create_journal_graph_persistent, create_journal_graph_postgres, JournalGraph
from .thread_manager import ThreadManager, ThreadMetadata

__all__ = [
    # State
    "JournalState",
    "SessionMode",
    "PendingEntity",
    "PartialEvent",
    "UsageRecord",
    "ToolCallRecord",
    "get_initial_state",
    "state_to_summary",
    # Graph
    "create_journal_graph",
    "create_journal_graph_persistent",
    "create_journal_graph_postgres",
    "JournalGraph",
    # Thread Management
    "ThreadManager",
    "ThreadMetadata",
]

