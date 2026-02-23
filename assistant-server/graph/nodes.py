"""
LangGraph Node Functions for Journal Agent.

Each node is a function that takes the state and returns state updates.
Nodes correspond to boxes in the ARCHITECTURE.md flow diagram.

Node Overview:
    - update_history: Process user message, update turn count
    - detect_context: Detect date, intent hints from message
    - route_message: Decide if journal-related or friendly chat
    - build_skeleton: Build timeline skeleton for target date
    - prepare_llm_context: Load skills, build system prompt
    - call_llm: Make LLM API call
    - execute_tools: Execute tool calls from LLM
    - store_turn: Record turn, check if distillation needed
    - friendly_chat: Handle non-journal conversations
"""

import re
import logging
import json
from datetime import date, datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from .state import JournalState, SessionMode, UsageRecord

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Constants for Request-Level Distillation
# -----------------------------------------------------------------------------

# Threshold for tool result size that triggers summarization (in chars)
TOOL_RESULT_SUMMARY_THRESHOLD = 1500

# After this many requests in a turn, summarize older tool results
REQUESTS_BEFORE_DISTILL = 3


# -----------------------------------------------------------------------------
# Distillation Integration
# -----------------------------------------------------------------------------

# Per-thread distillation helpers (keyed by thread_id)
_thread_distillers: dict[str, Any] = {}

# Module-level usage callback for persisting distillation usage to ledger
_usage_callback: Optional[callable] = None


def set_distillation_usage_callback(callback: Optional[callable]):
    """Set the callback for persisting distillation usage to ledger.
    
    Args:
        callback: Function(thread_id, input_tokens, output_tokens, model_provider, model_name)
    """
    global _usage_callback
    _usage_callback = callback


def get_thread_distiller(thread_id: str):
    """Get or create a DistillationHelper for a specific thread."""
    global _thread_distillers
    
    if thread_id not in _thread_distillers:
        from distillation import DistillationHelper, DistillationConfig
        from config import DISTILLATION_LLM_CONFIG
        from llm_clients import create_llm_client
        
        try:
            llm_client = create_llm_client(DISTILLATION_LLM_CONFIG)
        except Exception as e:
            logger.warning(f"Failed to create distillation LLM client: {e}. Using local rules.")
            llm_client = None
        
        # If LLM client creation failed, use local rules
        use_local_rules = llm_client is None
        
        config = DistillationConfig(
            recent_messages_full=6,
            recent_tool_results_full=4,
            summarize_threshold=TOOL_RESULT_SUMMARY_THRESHOLD,
            max_summary_chars=2000,
            include_reference_index=True
        )
        _thread_distillers[thread_id] = DistillationHelper(
            llm_client, config, 
            use_local_rules=use_local_rules,
            usage_callback=_usage_callback,
            thread_id=thread_id
        )
        logger.info(f"Created DistillationHelper for thread {thread_id} (local_rules={use_local_rules})")
    
    return _thread_distillers[thread_id]


def reset_thread_distiller(thread_id: str):
    """Reset distillation state for a thread."""
    global _thread_distillers
    if thread_id in _thread_distillers:
        _thread_distillers[thread_id].reset()
        del _thread_distillers[thread_id]


def _register_expand_reference_tool(mcp_bridge, thread_id: str):
    """Register the expand_reference internal tool for a thread."""
    distiller = get_thread_distiller(thread_id)
    
    def expand_reference_handler(arguments: dict) -> str:
        ref_id = arguments.get("ref_id", "")
        content = distiller.expand_reference(ref_id)
        if content:
            return f"[Expanded {ref_id}]\n{content}"
        else:
            available = list(distiller.references.keys())[:10]
            return f"Reference {ref_id} not found. Available: {available}"
    
    # Only register if not already present
    if "expand_reference" not in mcp_bridge.tool_names:
        mcp_bridge.register_internal_tool(
            name="expand_reference",
            description="Expand a reference ID to get the full content. Use when you need more detail about summarized content from earlier in the conversation.",
            input_schema={
                "type": "object",
                "properties": {
                    "ref_id": {
                        "type": "string",
                        "description": "The reference ID to expand (e.g., 'ref_abc123')"
                    }
                },
                "required": ["ref_id"]
            },
            handler=expand_reference_handler
        )


# -----------------------------------------------------------------------------
# Helper: Summarize Tool Result
# -----------------------------------------------------------------------------

# Singleton distillation LLM client (lazy-loaded)
_distillation_llm_client = None

def _get_distillation_llm():
    """Get or create the lightweight LLM client for distillation."""
    global _distillation_llm_client
    if _distillation_llm_client is None:
        from config import DISTILLATION_LLM_CONFIG
        from llm_clients import create_llm_client
        _distillation_llm_client = create_llm_client(DISTILLATION_LLM_CONFIG)
        logger.info(f"Created distillation LLM: {DISTILLATION_LLM_CONFIG.model}")
    return _distillation_llm_client


async def _summarize_tool_result(
    tool_name: str, 
    tool_args: dict, 
    result: str, 
    llm_client: Any = None
) -> str:
    """
    Summarize a large tool result using a lightweight LLM.
    
    Uses the dedicated distillation LLM (gpt-4o-mini) to extract essential info
    while dramatically reducing token count.
    """
    if len(result) < TOOL_RESULT_SUMMARY_THRESHOLD:
        return result  # No summarization needed
    
    # Use distillation LLM if no client provided
    if llm_client is None:
        llm_client = _get_distillation_llm()
    
    try:
        from llm_clients import Message as LLMMessage
        
        # Build a summarization prompt that preserves key data
        summary_prompt = f"""Summarize this tool result concisely. Preserve ALL key data (IDs, names, counts, dates, values).

Tool: {tool_name}
Arguments: {json.dumps(tool_args)[:200]}

Result ({len(result)} chars):
{result[:4000]}

Provide a concise summary (2-5 sentences) that preserves:
- Any IDs, UUIDs, or keys (these are CRITICAL for follow-up tool calls!)
- Names of people, places, events
- Counts, dates, numeric values
- Success/error status
- Key findings or matched items

Summary:"""

        response = await llm_client.chat(
            messages=[LLMMessage(role="user", content=summary_prompt)],
            tools=[],  # No tools for summarization
        )
        
        if response.content:
            summary = response.content.strip()
            return f"[Summarized from {len(result)} chars by distillation LLM]\n{summary}"
        else:
            # Fallback to smart truncation if summarization fails
            return _smart_truncate_tool_result(result, "fallback")
            
    except Exception as e:
        logger.warning(f"LLM summarization failed, using smart truncation: {e}")
        # Fallback to smart truncation
        return _smart_truncate_tool_result(result, "fallback")


def _smart_truncate_tool_result(result: str, tool_call_id: str) -> str:
    """
    Smart truncation that preserves key information patterns in tool results.
    
    This is better than simple truncation because it:
    1. Preserves UUIDs and IDs (critical for subsequent tool calls)
    2. Preserves counts and numeric values
    3. Preserves names and key identifiers
    4. Keeps the structure hints (JSON brackets, etc.)
    """
    if len(result) < TOOL_RESULT_SUMMARY_THRESHOLD:
        return result
    
    import re
    
    # Extract key patterns to preserve
    preserved_parts = []
    
    # Find all UUIDs (critical for tool follow-ups)
    uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', result, re.I)
    if uuids:
        unique_uuids = list(dict.fromkeys(uuids))[:10]  # Keep up to 10 unique UUIDs
        preserved_parts.append(f"IDs found: {', '.join(unique_uuids)}")
    
    # Find count patterns like "count": 5 or "returned 12 rows"
    count_patterns = re.findall(r'(?:"count":\s*(\d+)|returned\s+(\d+)\s+rows?|(\d+)\s+(?:results?|items?|records?))', result, re.I)
    if count_patterns:
        counts = [c for group in count_patterns for c in group if c]
        if counts:
            preserved_parts.append(f"Counts: {', '.join(counts[:5])}")
    
    # Find canonical_name patterns
    names = re.findall(r'"canonical_name":\s*"([^"]+)"', result)
    if names:
        unique_names = list(dict.fromkeys(names))[:8]
        preserved_parts.append(f"Names: {', '.join(unique_names)}")
    
    # Find success/error indicators
    if '"success": true' in result.lower() or '"success":true' in result.lower():
        preserved_parts.append("Status: success")
    elif '"error"' in result.lower():
        error_match = re.search(r'"error":\s*"([^"]{1,100})', result)
        if error_match:
            preserved_parts.append(f"Error: {error_match.group(1)}")
    
    # Build smart truncation
    header = f"[Smart summary of {len(result)} chars]\n"
    
    if preserved_parts:
        key_info = "\n".join(f"• {p}" for p in preserved_parts)
        # Include some raw content for context
        raw_preview = result[:800].strip()
        return f"{header}Key extracted info:\n{key_info}\n\nPreview:\n{raw_preview}..."
    else:
        # No patterns found, just truncate with note
        return result[:TOOL_RESULT_SUMMARY_THRESHOLD] + f"\n\n... [truncated {len(result) - TOOL_RESULT_SUMMARY_THRESHOLD} chars]"


def _estimate_message_tokens(content: str) -> int:
    """Rough estimate of tokens in a string (4 chars ≈ 1 token)."""
    return len(content) // 4


# -----------------------------------------------------------------------------
# Shared Dependencies (injected via graph config)
# -----------------------------------------------------------------------------

# These are passed through LangGraph's config.configurable dict:
# - mcp_bridge: MCPToolBridge instance for tool calls
# - llm_client: LLM client for chat completions
# - skeleton_builder: TimelineSkeletonBuilder instance
# - skills_loader: SkillsLoader instance


# -----------------------------------------------------------------------------
# Node: update_history
# -----------------------------------------------------------------------------

def update_history(state: JournalState) -> dict:
    """
    Process incoming user message and update conversation state.
    
    This node:
    1. Increments turn count
    2. Updates last_updated timestamp
    3. Resets request counter and tool summaries for new turn
    
    Note: The user message is already added to state.messages by the graph
    via the add_messages reducer before this node runs.
    """
    return {
        "turn_count": state.get("turn_count", 0) + 1,
        "last_updated": datetime.now().isoformat(),
        "current_turn_tools": [],  # Reset for new turn
        "tool_calls_remaining": 10,  # Reset tool round counter
        "request_count": 0,  # Reset request counter for new turn
        "tool_summaries": {},  # Reset tool summaries for new turn
    }


# -----------------------------------------------------------------------------
# Node: skill_router  (replaces detect_context)
# -----------------------------------------------------------------------------

# Skills that work with journal tools and may need skeleton building on log intent
JOURNAL_SKILLS = {"journal", "daily-tracker", "done", "retro"}

# All known skill names (slash command names)
ALL_SKILLS = {
    "journal", "daily-tracker", "email-triage", "expenses",
    "financial-advisor", "retro", "done", "kusto", "create-ado",
}


def skill_router(state: JournalState) -> dict:
    """
    Top-level skill router — determines which skill handles this message.

    Priority:
    1. Explicit slash command: /journal, /daily-tracker, /email-triage, etc.
    2. Session continuation: if a skill is already active, stay in it
    3. Journal intent detection: fall back to journal skill for journal-like messages
    4. friendly_chat: everything else

    Sets active_skill in state, routes to build_skeleton or prepare_llm.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"route": "prepare_llm"}

    latest_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_message = msg.content
            break

    if not latest_message:
        return {"route": "prepare_llm"}

    message_lower = latest_message.lower().strip()
    updates: dict = {}

    # 1. Explicit slash command
    detected_skill = None
    if message_lower.startswith("/"):
        first_word = message_lower.split()[0][1:]  # strip leading /
        if first_word in ALL_SKILLS:
            detected_skill = first_word
            logger.debug(f"Slash command detected: /{detected_skill}")

    # 2. Inherit active skill if session is ongoing
    if not detected_skill:
        current_skill = state.get("active_skill", "journal")
        current_mode = state.get("mode", SessionMode.IDLE.value)
        if current_mode in [SessionMode.LOGGING.value, SessionMode.QUERYING.value]:
            detected_skill = current_skill

    # 3. Journal intent detection (idle session, no command)
    if not detected_skill:
        journal_keywords = [
            "journal", "log", "logged", "entry", "yesterday", "today", "last week",
            "ate", "had", "went", "workout", "gym", "run", "ran", "meal", "breakfast",
            "lunch", "dinner", "work", "meeting", "slept", "sleep", "commute",
            "drove", "uber", "swiggy", "zomato", "did", "played", "tennis", "walked"
        ]
        if any(kw in message_lower for kw in journal_keywords):
            detected_skill = "journal"

    # 4. Fallback
    if not detected_skill:
        return {"route": "friendly_chat"}

    updates["active_skill"] = detected_skill

    # For journal-family skills: detect date + logging intent for skeleton building
    if detected_skill in JOURNAL_SKILLS:
        detected_date = _detect_date(latest_message)
        is_logging, _, _ = _detect_intent_hints(latest_message)

        if detected_date:
            updates["target_date"] = detected_date.isoformat()
            updates["mode"] = SessionMode.LOGGING.value if is_logging else SessionMode.QUERYING.value

        updates["route"] = "build_skeleton" if (is_logging and detected_date) else "prepare_llm"
    else:
        # Non-journal skills go straight to LLM — no skeleton needed
        updates["route"] = "prepare_llm"

    return updates


# Alias so graph.py import still works during transition
detect_context = skill_router


def _detect_date(message: str) -> Optional[date]:
    """
    Detect date references in a message.
    
    Supports:
    - Relative: "today", "yesterday", "last Monday"
    - ISO: "2025-01-15"
    - US format: "1/15/2025" or "1/15"
    - Natural: "January 15", "15th January"
    """
    today = date.today()
    message_lower = message.lower()
    
    # Relative dates
    if "today" in message_lower:
        return today
    if "yesterday" in message_lower:
        return today - __import__("datetime").timedelta(days=1)
    
    # Day of week references
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(weekdays):
        if f"last {day}" in message_lower:
            # Find the last occurrence of this weekday
            days_ago = (today.weekday() - i) % 7
            if days_ago == 0:
                days_ago = 7  # "last Monday" when today is Monday means 7 days ago
            return today - __import__("datetime").timedelta(days=days_ago)
    
    # ISO format: 2025-01-15
    iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', message)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass
    
    # US format: 1/15/2025 or 1/15
    us_match = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', message)
    if us_match:
        try:
            year = int(us_match.group(3)) if us_match.group(3) else today.year
            return date(year, int(us_match.group(1)), int(us_match.group(2)))
        except ValueError:
            pass
    
    # Month name patterns
    months = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
        'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    
    for month_name, month_num in months.items():
        # "December 25" or "Dec 25th"
        pattern = rf'{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?'
        match = re.search(pattern, message_lower)
        if match:
            try:
                return date(today.year, month_num, int(match.group(1)))
            except ValueError:
                pass
        
        # "25 December" or "25th of December"
        pattern = rf'(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?{month_name}'
        match = re.search(pattern, message_lower)
        if match:
            try:
                return date(today.year, month_num, int(match.group(1)))
            except ValueError:
                pass
    
    return None


def _detect_intent_hints(message: str) -> tuple[bool, bool, bool]:
    """
    Detect intent hints from message.
    
    Returns:
        Tuple of (is_logging, mentions_workout, mentions_meal)
    """
    message_lower = message.lower()
    
    # Logging indicators
    logging_phrases = [
        "adding", "add entry", "journal for", "log for", "logging",
        "entry for", "here's what", "i did", "what happened",
        "i had", "i went", "i ate", "i worked"
    ]
    is_logging = any(phrase in message_lower for phrase in logging_phrases)
    
    # Workout mentions
    workout_words = ["workout", "gym", "run", "ran", "exercise", "tennis", "swim", "walk", "hike", "played"]
    mentions_workout = any(word in message_lower for word in workout_words)
    
    # Meal mentions
    meal_words = ["breakfast", "lunch", "dinner", "ate", "meal", "food", "restaurant", "swiggy", "zomato"]
    mentions_meal = any(word in message_lower for word in meal_words)
    
    return is_logging, mentions_workout, mentions_meal


# -----------------------------------------------------------------------------
# Node: build_skeleton (async)
# -----------------------------------------------------------------------------

async def build_skeleton(state: JournalState, config: RunnableConfig) -> dict:
    """
    Build timeline skeleton for the target date.
    
    This node is only called when:
    1. User has logging intent
    2. A target date is detected
    3. The date is different from the current skeleton
    
    Requires config.configurable.skeleton_builder.
    """
    target_date_str = state.get("target_date")
    if not target_date_str:
        return {"route": "prepare_llm"}
    
    target_date = date.fromisoformat(target_date_str)
    
    # Check if we already have a skeleton for this date
    current_skeleton = state.get("skeleton")
    if current_skeleton and current_skeleton.get("date") == target_date_str:
        logger.debug(f"Using cached skeleton for {target_date}")
        return {"route": "prepare_llm"}
    
    # Get skeleton builder from config
    skeleton_builder = config.get("configurable", {}).get("skeleton_builder")
    if not skeleton_builder:
        logger.warning("No skeleton builder in config - skipping skeleton build")
        return {"route": "prepare_llm"}
    
    logger.info(f"Building skeleton for {target_date}...")
    
    try:
        skeleton = await skeleton_builder.build(target_date)
        
        # Serialize skeleton to dict for state
        skeleton_dict = {
            "date": target_date.isoformat(),
            "blocks": [
                {
                    "start_time": b.start_time.isoformat(),
                    "end_time": b.end_time.isoformat() if b.end_time else None,
                    "block_type": b.block_type,
                    "title": b.title,
                    "source": b.source,
                    "confidence": b.confidence.value,
                    "db_event_id": b.db_event_id,
                    "external_id": b.external_id,
                }
                for b in skeleton.blocks
            ],
            "gaps": [
                {
                    "start_time": g.start_time.isoformat(),
                    "end_time": g.end_time.isoformat(),
                    "likely_type": g.likely_type,
                    "duration_minutes": g.duration_minutes,
                }
                for g in skeleton.gaps
            ],
            "unplaced": [
                {
                    "timestamp": u.timestamp.isoformat(),
                    "event_type": u.event_type,
                    "source": u.source,
                    "description": u.description,
                }
                for u in skeleton.unplaced
            ],
            "summary": skeleton.to_summary(),
        }
        
        logger.info(f"Skeleton built: {len(skeleton.blocks)} blocks, {len(skeleton.gaps)} gaps")
        
        return {
            "skeleton": skeleton_dict,
            "route": "prepare_llm",
        }
        
    except Exception as e:
        logger.error(f"Failed to build skeleton: {e}")
        return {"route": "prepare_llm"}


# -----------------------------------------------------------------------------
# Node: prepare_llm_context (async)
# -----------------------------------------------------------------------------

async def prepare_llm_context(state: JournalState, config: RunnableConfig) -> dict:
    """
    Prepare context for LLM call: load active skill + user context.

    - Loads the active skill's content (set by skill_router)
    - Loads user-context.md and daily-context.json (once per session)
    - Requires config.configurable.skills_loader
    """
    skills_loader = config.get("configurable", {}).get("skills_loader")

    skills_content = ""
    user_context = state.get("user_context", "")

    if skills_loader:
        active_skill = state.get("active_skill", "journal")
        mode_str = state.get("mode", "idle")

        # Map session mode to skill sub-mode for support file selection
        mode_map = {
            SessionMode.LOGGING.value: "logging",
            SessionMode.QUERYING.value: "querying",
        }
        skill_mode = mode_map.get(mode_str)

        skills_content = skills_loader.load_skill_content(active_skill, mode=skill_mode)

        # Load user context once per session (cache in state)
        if not user_context:
            user_context_md = skills_loader.load_user_context()
            daily_context = skills_loader.load_daily_context()
            parts = []
            if user_context_md:
                parts.append(user_context_md)
            if daily_context:
                parts.append(daily_context)
            user_context = "\n\n".join(parts)

    return {
        "skills_content": skills_content,
        "user_context": user_context,
        "route": "call_llm",
    }


# -----------------------------------------------------------------------------
# Node: call_llm (async)
# -----------------------------------------------------------------------------

async def call_llm(state: JournalState, config: RunnableConfig) -> dict:
    """
    Make LLM API call with current context and tools.
    
    Uses DistillationHelper for intelligent context management:
    - Recent messages kept in full
    - Older messages summarized with references for on-demand expansion
    - Tool results intelligently compressed
    
    Requires:
    - config.configurable.llm_client
    - config.configurable.mcp_bridge (for tools)
    - config.configurable.skills_loader (for base prompt)
    """
    llm_client = config.get("configurable", {}).get("llm_client")
    mcp_bridge = config.get("configurable", {}).get("mcp_bridge")
    skills_loader = config.get("configurable", {}).get("skills_loader")
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    
    if not llm_client:
        raise RuntimeError("No LLM client configured")
    
    # Get or create distillation helper for this thread
    distiller = get_thread_distiller(thread_id)
    
    # Register expand_reference tool if we have mcp_bridge
    if mcp_bridge:
        _register_expand_reference_tool(mcp_bridge, thread_id)
    
    # Build system prompt
    base_prompt = skills_loader.get_base_prompt() if skills_loader else ""
    skills_content = state.get("skills_content", "")
    
    # Add session context
    from .state import state_to_summary
    session_summary = state_to_summary(state)
    
    system_parts = [base_prompt]

    # Inject user context (identity + daily state)
    user_context = state.get("user_context", "")
    if user_context:
        system_parts.append(f"\n## User Context\n{user_context}")

    system_parts.append(f"\n## Current Session\n{session_summary}")

    # Add owner ID if cached
    owner_id = state.get("owner_id")
    if owner_id:
        system_parts.append(f"\n## Cached Data\nOwner person_id: `{owner_id}`")

    # Add skeleton if in logging mode
    mode = state.get("mode")
    skeleton = state.get("skeleton")
    if skeleton and mode == SessionMode.LOGGING.value:
        system_parts.append(f"\n## Timeline Context\n{skeleton.get('summary', '')}")

    # Add active skill instructions
    if skills_content:
        system_parts.append(f"\n## Skill Instructions\n{skills_content}")
    
    system_prompt = "\n".join(system_parts)
    
    # Get tools — filtered to the active skill's allowed servers
    tools = []
    if mcp_bridge:
        from config import LLMProvider
        from skills import SKILL_ALLOWED_SERVERS
        provider = llm_client.config.provider if hasattr(llm_client, 'config') else LLMProvider.CLAUDE

        active_skill = state.get("active_skill", "journal")
        allowed_servers = SKILL_ALLOWED_SERVERS.get(active_skill)  # None = unrestricted

        provider_str = "claude" if provider == LLMProvider.CLAUDE else "openai"
        tools = mcp_bridge.to_filtered_tools(allowed_servers, provider=provider_str)

        logger.info(
            f"call_llm: skill={active_skill}, provider={provider.value}, "
            f"tools={len(tools)} (servers: {allowed_servers or 'all'})"
        )
    
    # Use DistillationHelper to build optimized message context
    from llm_clients import Message as LLMMessage, ToolCall
    import asyncio
    
    all_messages = state.get("messages", [])
    turn_count = state.get("turn_count", 1)
    request_count = state.get("request_count", 0)
    
    # Get distilled context from helper
    distilled_context = await distiller.distill(all_messages, turn_count)
    
    messages = []
    
    # Add distilled summary and reference index as context
    context_prompt = distiller.build_context_prompt(distilled_context)
    if context_prompt:
        messages.append(LLMMessage(role="user", content=f"[Context from earlier in conversation]\n{context_prompt}"))
        messages.append(LLMMessage(role="assistant", content="I have that context. I can use expand_reference to get full details if needed."))
    
    # Add recent messages (already in dict format from distiller)
    for msg_dict in distilled_context.recent_messages:
        role = msg_dict.get("role", "")
        content = msg_dict.get("content", "")
        
        if role == "user":
            messages.append(LLMMessage(role="user", content=content))
        elif role == "assistant":
            if msg_dict.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        arguments=tc.get("args", {})
                    )
                    for tc in msg_dict["tool_calls"]
                ]
                messages.append(LLMMessage(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls
                ))
            else:
                messages.append(LLMMessage(role="assistant", content=content))
        elif role == "tool":
            messages.append(LLMMessage(
                role="tool",
                content=content,
                tool_call_id=msg_dict.get("tool_call_id", "")
            ))
    
    logger.info(
        f"Distillation: {len(all_messages)} msgs → {len(messages)} context msgs, "
        f"{len(distilled_context.reference_index)} refs available, "
        f"compression: {distilled_context.get_compression_ratio():.2f}"
    )
    
    # Get thread_id for logging
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    
    # Log the request
    from llm_logger import get_llm_logger
    llm_logger = get_llm_logger()
    provider = llm_client.config.provider.value if hasattr(llm_client, 'config') else "unknown"
    model = llm_client.config.model if hasattr(llm_client, 'config') else "unknown"
    
    # Get or start turn for this thread
    # The turn number is based on how many LLM requests we've made in this thread
    turn = state.get("turn_count", 1)
    
    # Convert messages to dicts for logging
    messages_for_log = [
        {
            "role": m.role,
            "content": m.content,
            "tool_calls": [{"id": tc.id, "name": tc.name, "args": tc.arguments} for tc in m.tool_calls] if m.tool_calls else None,
            "tool_call_id": m.tool_call_id
        }
        for m in messages
    ]
    
    request_id = llm_logger.log_request(
        thread_id=thread_id,
        provider=provider,
        model=model,
        messages=messages_for_log,
        tools=tools,
        system_prompt=system_prompt,
        turn=turn,
    )
    
    # Check for streaming callback
    stream_callback = config.get("configurable", {}).get("stream_callback")
    
    # Make LLM call (with optional streaming)
    error_msg = None
    try:
        if stream_callback and hasattr(llm_client, 'stream_chat'):
            # Use streaming - accumulate response while sending chunks
            response = None
            async for chunk in llm_client.stream_chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt
            ):
                if chunk["type"] == "content":
                    # Send streaming token to callback
                    await stream_callback(chunk["content"])
                elif chunk["type"] == "done":
                    response = chunk["response"]
            
            if response is None:
                raise RuntimeError("Streaming completed without final response")
        else:
            # Non-streaming call
            response = await llm_client.chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt
            )
    except Exception as e:
        error_msg = str(e)
        # Log the error
        llm_logger.log_response(
            thread_id=thread_id,
            request_id=request_id,
            content="",
            tool_calls=[],
            stop_reason="error",
            usage={"input_tokens": 0, "output_tokens": 0},
            error=error_msg,
            turn=turn,
        )
        raise
    
    # Log the response
    llm_logger.log_response(
        thread_id=thread_id,
        request_id=request_id,
        content=response.content,
        tool_calls=[{"id": tc.id, "name": tc.name, "args": tc.arguments} for tc in response.tool_calls],
        stop_reason=response.stop_reason,
        usage=response.usage,
        turn=turn,
    )
    
    logger.info(f"LLM response: stop_reason={response.stop_reason}, tool_calls={len(response.tool_calls)}")
    if response.tool_calls:
        logger.info(f"Tool calls: {[tc.name for tc in response.tool_calls]}")
    
    # Track usage (usage is a dict with input_tokens and output_tokens)
    input_tokens = response.usage.get("input_tokens", 0) if response.usage else 0
    output_tokens = response.usage.get("output_tokens", 0) if response.usage else 0
    
    usage_record = {
        "timestamp": datetime.now().isoformat(),
        "provider": llm_client.config.provider.value if hasattr(llm_client, 'config') else "unknown",
        "model": llm_client.config.model if hasattr(llm_client, 'config') else "unknown",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    
    # Update totals
    total_input = state.get("total_input_tokens", 0) + input_tokens
    total_output = state.get("total_output_tokens", 0) + output_tokens
    
    # Update request count
    new_request_count = request_count + 1
    
    # Build response message
    if response.tool_calls:
        # LLM wants to use tools
        # Check if we have tool rounds remaining
        tool_calls_remaining = state.get("tool_calls_remaining", 10)
        
        if tool_calls_remaining <= 0:
            # Bug #4 fix: Don't allow infinite tool loops
            # Force a final response when tool budget is exhausted
            logger.warning(f"Tool budget exhausted. Forcing final response.")
            ai_message = AIMessage(
                content=response.content or "I've made several tool calls to process your request. The results have been applied, but I ran out of my reasoning budget before I could provide a summary. Please check the results or ask a follow-up question."
            )
            return {
                "messages": [ai_message],
                "usage_records": state.get("usage_records", []) + [usage_record],
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "request_count": new_request_count,
                "route": "store_turn",
            }
        
        ai_message = AIMessage(
            content=response.content or "",
            tool_calls=[
                {
                    "id": tc.id,
                    "name": tc.name,
                    "args": tc.arguments,
                }
                for tc in response.tool_calls
            ]
        )
        
        logger.info(f"Request #{new_request_count} in turn: {len(response.tool_calls)} tool calls")
        
        return {
            "messages": [ai_message],
            "usage_records": state.get("usage_records", []) + [usage_record],
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "request_count": new_request_count,
            "route": "execute_tools",
            "tool_calls_remaining": tool_calls_remaining - 1,
        }
    else:
        # Final response - check for empty response (Bug #4)
        content = response.content
        if not content or not content.strip():
            logger.warning("LLM returned empty response without tool calls")
            content = "I processed your request but couldn't generate a text response. This sometimes happens when the model uses all its output capacity for reasoning. Please try rephrasing or ask a follow-up question."
        
        ai_message = AIMessage(content=content)
        
        return {
            "messages": [ai_message],
            "usage_records": state.get("usage_records", []) + [usage_record],
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "request_count": new_request_count,
            "route": "store_turn",
        }


# -----------------------------------------------------------------------------
# Node: execute_tools (async)
# -----------------------------------------------------------------------------

async def execute_tools(state: JournalState, config: RunnableConfig) -> dict:
    """
    Execute tool calls from the LLM response.
    
    Requires config.configurable.mcp_bridge.
    """
    mcp_bridge = config.get("configurable", {}).get("mcp_bridge")
    if not mcp_bridge:
        logger.error("No MCP bridge configured for tool execution")
        return {"route": "call_llm"}
    
    # Get thread_id for logging
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    
    # Get the latest AI message with tool calls
    messages = state.get("messages", [])
    latest_ai_msg = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            latest_ai_msg = msg
            break
    
    if not latest_ai_msg or not latest_ai_msg.tool_calls:
        logger.warning("No tool calls found in latest message")
        return {"route": "call_llm"}
    
    logger.info(f"execute_tools: Found {len(latest_ai_msg.tool_calls)} tool calls to execute")
    
    tool_results = []
    tool_records = state.get("current_turn_tools", [])
    
    for tool_call in latest_ai_msg.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        logger.info(f"Executing tool: {tool_name}")
        
        start_time = datetime.now()
        error_str = None
        try:
            result = await mcp_bridge.call_tool(tool_name, tool_args)
            result_str = str(result) if not isinstance(result, str) else result
        except Exception as e:
            logger.error(f"Tool error: {e}")
            result_str = f"Error executing tool: {e}"
            error_str = str(e)
        
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Log tool execution
        from llm_logger import get_llm_logger
        llm_logger = get_llm_logger()
        turn = state.get("turn_count", 1)
        llm_logger.log_tool_execution(
            thread_id=thread_id,
            tool_name=tool_name,
            arguments=tool_args,
            result=result_str,
            duration_ms=duration_ms,
            error=error_str,
            turn=turn,
        )
        
        # Record tool call
        tool_records.append({
            "name": tool_name,
            "arguments": tool_args,
            "result": result_str[:500] if len(result_str) > 500 else result_str,
            "timestamp": start_time.isoformat(),
            "duration_ms": duration_ms,
        })
        
        # Create tool message
        tool_results.append(ToolMessage(
            content=result_str,
            tool_call_id=tool_id,
        ))
    
    # Check if we should continue or hit max rounds
    remaining = state.get("tool_calls_remaining", 10)
    route = "call_llm" if remaining > 0 else "store_turn"
    
    return {
        "messages": tool_results,
        "current_turn_tools": tool_records,
        "route": route,
    }


# -----------------------------------------------------------------------------
# Node: store_turn
# -----------------------------------------------------------------------------

async def store_turn(state: JournalState, config: RunnableConfig) -> dict:
    """
    Store the completed turn and handle post-turn cleanup.
    
    The turn is automatically persisted by LangGraph's checkpointer.
    This node handles post-turn cleanup.
    
    Note: Distillation is now handled by DistillationHelper during call_llm,
    providing request-level distillation instead of turn-based.
    """
    turn_count = state.get("turn_count", 0)
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    
    updates = {
        "last_updated": datetime.now().isoformat(),
    }
    
    # Log distillation stats if available
    distiller = _thread_distillers.get(thread_id)
    if distiller:
        logger.info(
            f"Turn {turn_count} complete. Distillation: "
            f"{len(distiller.content_store)} items stored, "
            f"{len(distiller.references)} refs available"
        )
    
    # Generate title from first message if not set
    thread_title = state.get("thread_title", "New Conversation")
    if thread_title == "New Conversation" and turn_count == 1:
        messages = state.get("messages", [])
        for msg in messages:
            if isinstance(msg, HumanMessage):
                # Take first 50 chars of first user message
                first_msg = msg.content[:50]
                if len(msg.content) > 50:
                    first_msg += "..."
                updates["thread_title"] = first_msg
                break
    
    return updates


# -----------------------------------------------------------------------------
# Node: friendly_chat
# -----------------------------------------------------------------------------

def friendly_chat(state: JournalState) -> dict:
    """
    Handle non-journal-related conversation.
    
    This is a simple passthrough that marks the message for LLM handling
    but without loading skills or skeleton.
    """
    return {
        "skills_content": "",
        "skeleton": None,
        "route": "call_llm",
    }
