"""
LangGraph Graph Builder for Journal Agent.

Creates the compiled graph with nodes and edges matching the
ARCHITECTURE.md flow diagram.

Graph Structure:
    START → update_history → detect_context
    
    detect_context → (conditional)
        - "build_skeleton" → build_skeleton → prepare_llm → call_llm
        - "prepare_llm" → prepare_llm → call_llm
        - "friendly_chat" → friendly_chat → call_llm
    
    call_llm → (conditional)
        - "execute_tools" → execute_tools → call_llm (loop)
        - "store_turn" → store_turn → END
    
    execute_tools → (conditional)
        - tool_calls_remaining > 0 → call_llm
        - tool_calls_remaining == 0 → store_turn
"""

import logging
import aiosqlite
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from .state import JournalState, get_initial_state
from .nodes import (
    update_history,
    skill_router,
    detect_context,  # alias for skill_router — kept for backward compat
    build_skeleton,
    prepare_llm_context,
    call_llm,
    execute_tools,
    store_turn,
    friendly_chat,
)

logger = logging.getLogger(__name__)


def _route_after_detect(state: JournalState) -> str:
    """Route after detect_context based on state.route."""
    route = state.get("route", "prepare_llm")
    logger.debug(f"Routing after detect: {route}")
    return route


def _route_after_call_llm(state: JournalState) -> str:
    """Route after call_llm based on whether tools need execution."""
    route = state.get("route", "store_turn")
    logger.debug(f"Routing after LLM: {route}")
    return route


def _route_after_execute_tools(state: JournalState) -> str:
    """Route after tool execution based on remaining rounds."""
    route = state.get("route", "call_llm")
    logger.debug(f"Routing after tools: {route}")
    return route


def _build_graph(checkpointer: BaseCheckpointSaver) -> StateGraph:
    """
    Build and compile the graph with a given checkpointer.
    
    Internal function used by both sync and async graph creation.
    """
    # Build the graph
    builder = StateGraph(JournalState)
    
    # Add nodes
    builder.add_node("update_history", update_history)
    builder.add_node("detect_context", detect_context)
    builder.add_node("build_skeleton", build_skeleton)
    builder.add_node("prepare_llm", prepare_llm_context)
    builder.add_node("call_llm", call_llm)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("store_turn", store_turn)
    builder.add_node("friendly_chat", friendly_chat)
    
    # Set entry point
    builder.set_entry_point("update_history")
    
    # Add edges
    builder.add_edge("update_history", "detect_context")
    
    # Conditional routing after detect_context
    builder.add_conditional_edges(
        "detect_context",
        _route_after_detect,
        {
            "build_skeleton": "build_skeleton",
            "prepare_llm": "prepare_llm",
            "friendly_chat": "friendly_chat",
        }
    )
    
    builder.add_edge("build_skeleton", "prepare_llm")
    builder.add_edge("prepare_llm", "call_llm")
    builder.add_edge("friendly_chat", "call_llm")
    
    # Conditional routing after call_llm (tools or finish)
    builder.add_conditional_edges(
        "call_llm",
        _route_after_call_llm,
        {
            "execute_tools": "execute_tools",
            "store_turn": "store_turn",
        }
    )
    
    # Conditional routing after execute_tools (continue or finish)
    builder.add_conditional_edges(
        "execute_tools",
        _route_after_execute_tools,
        {
            "call_llm": "call_llm",
            "store_turn": "store_turn",
        }
    )
    
    # End node
    builder.add_edge("store_turn", END)
    
    # Compile with checkpointer
    graph = builder.compile(checkpointer=checkpointer)
    
    logger.info("Journal graph compiled successfully")
    
    return graph, builder


def create_journal_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    db_path: str = "journal_graph.db"
) -> "JournalGraph":
    """
    Create the compiled journal agent graph with in-memory storage.
    
    DEPRECATED: Use create_journal_graph_persistent() for persistent storage.
    
    Args:
        checkpointer: Optional custom checkpointer. If None, creates MemorySaver.
        db_path: Path for SQLite checkpoint database (unused in memory mode).
    
    Returns:
        JournalGraph wrapper with the compiled graph.
    """
    # Create checkpointer if not provided
    if checkpointer is None:
        checkpointer = MemorySaver()
    
    graph, builder = _build_graph(checkpointer)
    
    return JournalGraph(graph, builder, checkpointer, db_path, persistent=False)


async def create_journal_graph_persistent(
    db_path: str = "journal_checkpoints.db"
) -> "JournalGraph":
    """
    Create the compiled journal agent graph with persistent SQLite storage.
    
    This version persists conversation state across server restarts.
    
    Args:
        db_path: Path for SQLite checkpoint database.
    
    Returns:
        JournalGraph wrapper with the compiled graph.
    """
    # Create the async SQLite connection
    conn = await aiosqlite.connect(db_path)
    
    # Monkey-patch is_alive() method - langgraph-checkpoint-sqlite 3.0.1 expects this
    # but aiosqlite.Connection doesn't have it
    if not hasattr(conn, 'is_alive'):
        conn.is_alive = lambda: conn._connection is not None
    
    # Create the checkpointer with the connection
    checkpointer = AsyncSqliteSaver(conn)
    
    graph, builder = _build_graph(checkpointer)
    
    logger.info(f"Journal graph compiled with persistent storage: {db_path}")
    
    return JournalGraph(graph, builder, checkpointer, db_path, persistent=True, conn=conn)


async def create_journal_graph_postgres(pg_dsn: str) -> "JournalGraph":
    """
    Create the compiled journal agent graph with PostgreSQL storage (production).

    Uses AsyncPostgresSaver with a connection pool. Automatically creates the
    langgraph checkpoint tables in the target database if they don't exist.

    Args:
        pg_dsn: PostgreSQL connection string, e.g.
                "postgresql://user:pass@host:5432/assistant_system"

    Returns:
        JournalGraph wrapper backed by PostgreSQL.
    """
    try:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as e:
        raise ImportError(
            "PostgreSQL checkpointer requires: pip install psycopg[binary] psycopg-pool "
            "langgraph-checkpoint-postgres"
        ) from e

    # Open a small async connection pool — keeps connections alive for the server lifetime
    pool = AsyncConnectionPool(
        conninfo=pg_dsn,
        max_size=5,
        kwargs={"autocommit": True},
        open=False,
    )
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    # Creates langgraph checkpoint tables if they don't exist
    await checkpointer.setup()

    graph, builder = _build_graph(checkpointer)

    logger.info(f"Journal graph compiled with PostgreSQL storage")

    return JournalGraph(
        graph, builder, checkpointer, pg_dsn, persistent=True, pg_pool=pool
    )


class JournalGraph:
    """
    Wrapper around the compiled LangGraph.
    
    Provides a clean interface for:
    - Running conversations with automatic state persistence
    - Managing threads (via ThreadManager)
    - Configuring dependencies (MCP bridge, LLM client, etc.)
    
    Supports both in-memory (MemorySaver) and persistent (AsyncSqliteSaver) modes.
    """
    
    def __init__(
        self,
        graph,
        builder: StateGraph,
        checkpointer: Optional[BaseCheckpointSaver],
        db_path: str,
        persistent: bool = False,
        conn=None,       # aiosqlite connection (SQLite mode)
        pg_pool=None,    # AsyncConnectionPool (PostgreSQL mode)
    ):
        self.graph = graph
        self.builder = builder  # Keep builder for potential recompilation
        self.checkpointer = checkpointer
        self.db_path = db_path
        self.persistent = persistent
        self._conn = conn        # SQLite connection (SQLite mode only)
        self._pg_pool = pg_pool  # PostgreSQL connection pool (Postgres mode only)
        
        # Dependencies (set via configure())
        self._mcp_bridge = None
        self._llm_client = None
        self._skeleton_builder = None
        self._skills_loader = None
    
    async def setup(self):
        """
        Initialize resources.
        
        For persistent mode, the setup is done during creation.
        For memory mode, this is a no-op.
        """
        if self.persistent:
            logger.info(f"JournalGraph setup complete (persistent: {self.db_path})")
        else:
            logger.info("JournalGraph setup complete (in-memory)")
    
    async def cleanup(self):
        """Clean up resources (SQLite connection or PostgreSQL pool)."""
        if self._conn:
            try:
                await self._conn.close()
                logger.info("Closed SQLite checkpoint connection")
            except Exception as e:
                logger.warning(f"Error closing SQLite connection: {e}")
            self._conn = None

        if self._pg_pool:
            try:
                await self._pg_pool.close()
                logger.info("Closed PostgreSQL checkpoint pool")
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL pool: {e}")
            self._pg_pool = None
    
    def configure(
        self,
        mcp_bridge=None,
        llm_client=None,
        skeleton_builder=None,
        skills_loader=None,
    ) -> "JournalGraph":
        """
        Configure dependencies for the graph.
        
        Args:
            mcp_bridge: MCPToolBridge instance
            llm_client: LLM client instance
            skeleton_builder: TimelineSkeletonBuilder instance
            skills_loader: SkillsLoader instance
        
        Returns:
            Self for chaining.
        """
        if mcp_bridge:
            self._mcp_bridge = mcp_bridge
        if llm_client:
            self._llm_client = llm_client
        if skeleton_builder:
            self._skeleton_builder = skeleton_builder
        if skills_loader:
            self._skills_loader = skills_loader
        return self
    
    def _get_config(self, thread_id: str, stream_callback=None, mcp_bridge=None) -> dict:
        """
        Build config dict for graph invocation.

        Args:
            thread_id: Conversation thread ID.
            stream_callback: Optional streaming callback for token-by-token output.
            mcp_bridge: Per-user MCPToolBridge override. If None, uses the bridge
                        set via configure(). This enables multi-user isolation where
                        each user's session uses their own bridge with user-specific
                        credentials.
        """
        config = {
            "configurable": {
                "thread_id": thread_id,
                "mcp_bridge": mcp_bridge or self._mcp_bridge,
                "llm_client": self._llm_client,
                "skeleton_builder": self._skeleton_builder,
                "skills_loader": self._skills_loader,
            }
        }
        if stream_callback:
            config["configurable"]["stream_callback"] = stream_callback
        return config
    
    async def chat(
        self,
        message: str,
        thread_id: str,
        mcp_bridge=None,
    ) -> str:
        """
        Process a user message and return the assistant's response.

        Args:
            message: User's input message
            thread_id: Thread ID for conversation persistence
            mcp_bridge: Per-user MCPToolBridge override for multi-user isolation.

        Returns:
            Assistant's response text
        """
        from langchain_core.messages import HumanMessage, AIMessage

        # Create input state with user message
        input_state = {"messages": [HumanMessage(content=message)]}

        # Get config
        config = self._get_config(thread_id, mcp_bridge=mcp_bridge)
        
        # Run the graph
        result = await self.graph.ainvoke(input_state, config)
        
        # Extract assistant response from messages
        # Look for the last AIMessage without active tool calls
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                # Check if this message has tool calls (not just empty list)
                has_tool_calls = msg.tool_calls and len(msg.tool_calls) > 0
                if not has_tool_calls and msg.content:
                    return msg.content
        
        # Fallback: return any AIMessage content
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        
        return "I processed your request but couldn't generate a response."
    
    async def stream_chat(
        self,
        message: str,
        thread_id: str,
        stream_callback=None,
        mcp_bridge=None,
    ):
        """
        Stream the conversation processing.

        Yields state updates as the graph processes.

        Args:
            message: User's input message
            thread_id: Thread ID for conversation persistence
            stream_callback: Optional async callback(token: str) for streaming response tokens
            mcp_bridge: Per-user MCPToolBridge override for multi-user isolation.
        """
        from langchain_core.messages import HumanMessage

        input_state = {"messages": [HumanMessage(content=message)]}
        config = self._get_config(thread_id, stream_callback=stream_callback, mcp_bridge=mcp_bridge)
        
        async for event in self.graph.astream(input_state, config):
            yield event
    
    async def get_state(self, thread_id: str) -> Optional[JournalState]:
        """Get the current state for a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        try:
            # Use async aget_state for AsyncSqliteSaver
            state_snapshot = await self.graph.aget_state(config)
            return state_snapshot.values if state_snapshot else None
        except Exception as e:
            logger.error(f"Failed to get state for thread {thread_id}: {e}")
            return None
    
    async def get_messages(self, thread_id: str) -> list:
        """Get all messages for a thread (async for persistent storage)."""
        state = await self.get_state(thread_id)
        if state:
            return state.get("messages", [])
        return []
    
    def clear_thread(self, thread_id: str) -> bool:
        """Clear a thread's state (soft delete)."""
        # Note: LangGraph checkpointer doesn't support deletion directly
        # We'd need to implement this in ThreadManager with a separate table
        logger.warning("clear_thread not implemented - use ThreadManager")
        return False
