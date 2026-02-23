"""
LangGraph State Schema for Journal Agent.

Defines the TypedDict state that flows through the graph and persists
via the checkpointer. Maps directly from ARCHITECTURE.md SessionState.
"""

from typing import TypedDict, Annotated, Optional, Literal, Any
from datetime import date, datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class SessionMode(str, Enum):
    """Current session mode - matches ARCHITECTURE.md."""
    IDLE = "idle"
    LOGGING = "logging"
    QUERYING = "querying"


@dataclass
class PendingEntity:
    """
    An entity mentioned but not yet resolved.
    
    From ARCHITECTURE.md:
    - mention: "Sarah", "the gym", "that Thai place"
    - entity_type: "person", "location", "activity"
    - candidates: Possible matches from DB
    - resolved_id: UUID once resolved
    """
    mention: str
    entity_type: str  # "person", "location", "activity"
    candidates: list[dict] = field(default_factory=list)
    resolved_id: Optional[str] = None
    resolved_name: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PendingEntity":
        return cls(**data)


@dataclass
class PartialEvent:
    """
    An event being built across multiple turns.
    
    From ARCHITECTURE.md:
    - event_type: "meal", "workout", "generic"
    - known_fields: What we know so far
    - missing_fields: What we still need
    """
    event_type: str  # "meal", "workout", "generic"
    known_fields: dict = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PartialEvent":
        return cls(**data)


@dataclass
class UsageRecord:
    """Token and cost tracking for a single LLM call."""
    timestamp: datetime
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "UsageRecord":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            provider=data["provider"],
            model=data["model"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            cost_usd=data.get("cost_usd"),
        )


@dataclass
class ToolCallRecord:
    """Record of a tool call made during processing."""
    name: str
    arguments: dict
    result: str
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result[:500] if len(self.result) > 500 else self.result,  # Truncate large results
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }


# -----------------------------------------------------------------------------
# LangGraph State TypedDict
# -----------------------------------------------------------------------------

class JournalState(TypedDict, total=False):
    """
    LangGraph state that flows through the journal agent graph.
    
    This maps directly from ARCHITECTURE.md SessionState with additions
    for LangGraph's message management and usage tracking.
    
    Core State (from SessionState):
        messages: Annotated list for LangGraph's automatic message management
        mode: Current session mode (idle, logging, querying)
        target_date: Date being logged/queried (ISO format string)
        skeleton: Timeline skeleton as serialized dict
        pending_entities: Unresolved names/places
        pending_events: Partially built events
        turn_count: Number of conversation turns
        distilled_summary: Compressed older history
    
    Workflow Control:
        route: Next node to execute (used by conditional edges)
        tool_calls_remaining: Counter for max tool rounds
        current_turn_tools: Tool calls in current turn (for logging)
    
    Usage Tracking:
        usage_records: Token usage per LLM call
        total_tokens: Aggregated token count for thread
    
    Thread Metadata (for ThreadManager):
        thread_title: Display title
        created_at: Thread creation timestamp
        last_updated: Last activity timestamp
    """
    
    # Core LangGraph messages - uses add_messages reducer for automatic handling
    messages: Annotated[list[BaseMessage], add_messages]
    
    # Session state from ARCHITECTURE.md
    mode: str  # SessionMode value as string
    target_date: Optional[str]  # ISO format date string
    skeleton: Optional[dict]  # Serialized TimelineSkeleton
    pending_entities: list[dict]  # Serialized PendingEntity list
    pending_events: list[dict]  # Serialized PartialEvent list
    turn_count: int
    distilled_summary: str
    
    # Workflow control
    route: str  # Next node to route to
    tool_calls_remaining: int  # Countdown for tool rounds
    current_turn_tools: list[dict]  # Tool calls in this turn
    
    # Usage tracking
    usage_records: list[dict]  # Serialized UsageRecord list
    total_input_tokens: int
    total_output_tokens: int
    
    # Thread metadata
    thread_title: str
    created_at: str  # ISO format timestamp
    last_updated: str  # ISO format timestamp
    
    # Cached data
    owner_id: Optional[str]  # Cached owner person_id
    
    # Active skill — set by skill_router, persists across turns in a thread
    active_skill: str  # e.g., "journal", "daily-tracker", "email-triage"

    # User context — loaded from user-context.md + daily-context.json
    user_context: str

    # Skills content (injected based on context)
    skills_content: str
    
    # Request-level tracking (for intra-turn distillation)
    request_count: int  # Number of LLM requests in current turn
    tool_summaries: dict  # Map of tool_call_id -> summary (for distilled tool results)
    
    # Distillation state (managed by DistillationHelper)
    distillation_refs: dict  # Map of ref_id -> ContentReference metadata
    distillation_store: dict  # Map of ref_id -> full content (expandable)


def get_initial_state() -> JournalState:
    """Create initial state for a new thread."""
    now = datetime.now().isoformat()
    return JournalState(
        messages=[],
        mode=SessionMode.IDLE.value,
        target_date=None,
        skeleton=None,
        pending_entities=[],
        pending_events=[],
        turn_count=0,
        distilled_summary="",
        route="",
        tool_calls_remaining=10,
        current_turn_tools=[],
        usage_records=[],
        total_input_tokens=0,
        total_output_tokens=0,
        thread_title="New Conversation",
        created_at=now,
        last_updated=now,
        owner_id=None,
        active_skill="journal",  # Default to journal skill
        user_context="",
        skills_content="",
        request_count=0,
        tool_summaries={},
        distillation_refs={},
        distillation_store={},
    )


def state_to_summary(state: JournalState) -> str:
    """Generate summary string for LLM context (replaces SessionState.to_summary)."""
    parts = []
    
    mode = state.get("mode", SessionMode.IDLE.value)
    target_date = state.get("target_date")
    
    if mode == SessionMode.LOGGING.value:
        parts.append(f"Currently logging for {target_date}")
    elif mode == SessionMode.QUERYING.value:
        parts.append(f"Currently querying about {target_date or 'journal'}")
    else:
        parts.append("Idle - no active logging session")
    
    skeleton = state.get("skeleton")
    if skeleton:
        gap_count = len(skeleton.get("gaps", []))
        unplaced_count = len(skeleton.get("unplaced", []))
        if gap_count > 0:
            parts.append(f"{gap_count} gaps remaining")
        if unplaced_count > 0:
            parts.append(f"{unplaced_count} unplaced transactions")
    
    pending_entities = state.get("pending_entities", [])
    if pending_entities:
        unresolved = [e["mention"] for e in pending_entities if not e.get("resolved_id")]
        if unresolved:
            parts.append(f"Unresolved: {', '.join(unresolved)}")
    
    return ". ".join(parts) + "."
