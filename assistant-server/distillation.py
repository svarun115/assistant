"""
Distillation Helper for Journal Agent.

Manages intelligent context compression using a lightweight LLM.
Provides tiered access to information with reference IDs for on-demand expansion.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    Conversation Context                      │
    ├─────────────────────────────────────────────────────────────┤
    │  [Distilled Summary]   - High-level summary of older turns   │
    │  [Reference Index]     - Brief descriptions with ref IDs     │
    │  [Recent Full]         - Last N messages in full             │
    ├─────────────────────────────────────────────────────────────┤
    │  Content Store: ref_id → full content (expandable on demand) │
    └─────────────────────────────────────────────────────────────┘

The LLM can request expansion of any reference by calling expand_reference(ref_id).
"""

import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Types of content that can be stored and referenced."""
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TURN_SUMMARY = "turn_summary"


@dataclass
class ContentReference:
    """A reference to stored content that can be expanded on demand."""
    ref_id: str
    content_type: ContentType
    brief: str  # Short description for the reference index
    char_count: int
    turn_number: int
    timestamp: str
    tool_name: Optional[str] = None  # For tool calls/results
    

@dataclass
class DistilledContext:
    """
    The distilled context to send to the main LLM.
    
    Contains:
    - distilled_summary: High-level summary of older conversation
    - reference_index: List of expandable references
    - recent_messages: Recent messages in full (not distilled)
    - available_refs: Set of ref_ids that can be expanded
    """
    distilled_summary: str
    reference_index: list[ContentReference]
    recent_messages: list[dict]  # LLM message format
    available_refs: set[str] = field(default_factory=set)
    total_original_chars: int = 0
    total_distilled_chars: int = 0
    
    def get_compression_ratio(self) -> float:
        """Get the compression ratio achieved."""
        if self.total_original_chars == 0:
            return 1.0
        return self.total_distilled_chars / self.total_original_chars


@dataclass
class DistillationConfig:
    """Configuration for distillation behavior."""
    # How many recent messages to keep in full
    recent_messages_full: int = 6
    
    # How many recent tool results to keep in full
    recent_tool_results_full: int = 4
    
    # Character threshold for summarizing content
    summarize_threshold: int = 1500
    
    # Max chars for the distilled summary
    max_summary_chars: int = 2000
    
    # Max chars for reference briefs
    max_brief_chars: int = 150
    
    # Whether to include reference index in context
    include_reference_index: bool = True


class DistillationHelper:
    """
    Manages intelligent context distillation for the journal agent.
    
    Uses a lightweight LLM to summarize older content while preserving
    the ability to expand references on demand.
    
    ISOLATION GUARANTEES:
    ---------------------
    1. Uses SEPARATE LLM client (gpt-4o-mini via DISTILLATION_LLM_CONFIG)
       - Not the user's selected conversation LLM
       - Configured for low cost and fast summarization
    
    2. Distillation responses are NEVER added to conversation state
       - Internal to this helper only
       - Only summaries are used to build context for main LLM
    
    3. Does NOT go through LLM logger
       - Distillation calls are internal housekeeping
       - Won't pollute conversation logs
    
    4. NO recursive distillation
       - Works on state["messages"] which only contains actual conversation
       - Distilled summaries are stored separately in this helper
    
    Usage:
        helper = DistillationHelper(distillation_llm_client)
        
        # Before each LLM call, get distilled context
        context = await helper.distill(messages, current_turn)
        
        # LLM can request expansion of a reference
        full_content = helper.expand_reference("ref_abc123")
    """
    
    def __init__(
        self, 
        llm_client: Any = None, 
        config: Optional[DistillationConfig] = None,
        use_local_rules: bool = False,
        usage_callback: Optional[callable] = None,
        thread_id: Optional[str] = None,
    ):
        """
        Initialize the distillation helper.
        
        Args:
            llm_client: Lightweight LLM client for summarization (None if use_local_rules)
            config: Distillation configuration
            use_local_rules: If True, use rule-based truncation instead of LLM
            usage_callback: Optional callback(thread_id, input_tokens, output_tokens, model_provider, model_name)
                           to persist usage to a ledger
            thread_id: Thread ID for usage tracking
        """
        self.llm_client = llm_client
        self.config = config or DistillationConfig()
        self.use_local_rules = use_local_rules
        self.usage_callback = usage_callback
        self.thread_id = thread_id
        
        # Content store: ref_id -> full content
        self.content_store: dict[str, str] = {}
        
        # Reference metadata: ref_id -> ContentReference
        self.references: dict[str, ContentReference] = {}
        
        # Current distilled summary (cumulative)
        self.distilled_summary: str = ""
        
        # Track what's been distilled
        self.last_distilled_turn: int = 0
        
        # Usage tracking for distillation LLM calls
        self.usage_records: list[dict] = []
        
    def get_usage_stats(self) -> dict:
        """Get aggregated usage stats for distillation."""
        if not self.usage_records:
            return {"input_tokens": 0, "output_tokens": 0, "cost": 0, "calls": 0}
        
        total_input = sum(r.get("input_tokens", 0) for r in self.usage_records)
        total_output = sum(r.get("output_tokens", 0) for r in self.usage_records)
        total_cost = sum(r.get("cost", 0) for r in self.usage_records)
        
        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost": total_cost,
            "calls": len(self.usage_records),
            "model": self.usage_records[-1].get("model", "unknown") if self.usage_records else "unknown"
        }
    
    async def set_model(self, model_id: str) -> dict:
        """
        Change the distillation model at runtime.
        
        Args:
            model_id: One of 'gpt-5-nano', 'gpt-4o-mini', or 'local-rules'
            
        Returns:
            dict with status and new model info
        """
        from config import DISTILLATION_MODELS, DISTILLATION_LLM_CONFIG, LLMProvider
        
        # Check if valid model
        valid_ids = [m["id"] for m in DISTILLATION_MODELS]
        if model_id not in valid_ids:
            return {"success": False, "error": f"Unknown model: {model_id}. Valid: {valid_ids}"}
        
        if model_id == "local-rules":
            # Switch to local rules mode
            self.use_local_rules = True
            self.llm_client = None
            return {"success": True, "model": model_id, "mode": "local_rules"}
        else:
            # Switch to LLM-based mode
            from llm_clients import OpenAIClient, LLMConfig
            
            # Create new config with selected model
            new_config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model=model_id,
                api_key=DISTILLATION_LLM_CONFIG.api_key,
                base_url=DISTILLATION_LLM_CONFIG.base_url
            )
            self.llm_client = OpenAIClient(new_config)
            self.use_local_rules = False
            return {"success": True, "model": model_id, "mode": "llm"}
    
    def get_current_model(self) -> dict:
        """Get info about current distillation model."""
        if self.use_local_rules:
            return {"model": "local-rules", "mode": "local_rules"}
        elif self.llm_client and hasattr(self.llm_client, 'config'):
            return {"model": self.llm_client.config.model, "mode": "llm"}
        else:
            return {"model": "unknown", "mode": "unknown"}
        
    def _generate_ref_id(self, content: str, content_type: ContentType) -> str:
        """Generate a unique reference ID for content."""
        hash_input = f"{content_type.value}:{content[:100]}:{datetime.now().isoformat()}"
        return f"ref_{hashlib.md5(hash_input.encode()).hexdigest()[:8]}"
    
    def _store_content(
        self, 
        content: str, 
        content_type: ContentType,
        turn_number: int,
        brief: Optional[str] = None,
        tool_name: Optional[str] = None
    ) -> ContentReference:
        """Store content and create a reference for it."""
        ref_id = self._generate_ref_id(content, content_type)
        
        # Generate brief if not provided
        if brief is None:
            brief = self._generate_brief(content, content_type, tool_name)
        
        ref = ContentReference(
            ref_id=ref_id,
            content_type=content_type,
            brief=brief,
            char_count=len(content),
            turn_number=turn_number,
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name
        )
        
        self.content_store[ref_id] = content
        self.references[ref_id] = ref
        
        return ref
    
    def _generate_brief(
        self, 
        content: str, 
        content_type: ContentType,
        tool_name: Optional[str] = None
    ) -> str:
        """Generate a brief description for content."""
        max_len = self.config.max_brief_chars
        
        if content_type == ContentType.TOOL_RESULT:
            # Extract key info from tool result
            preview = content[:200].replace('\n', ' ')
            if tool_name:
                return f"[{tool_name}] {preview[:max_len-len(tool_name)-4]}..."
            return f"{preview[:max_len]}..."
            
        elif content_type == ContentType.TOOL_CALL:
            if tool_name:
                return f"Called {tool_name}"
            return content[:max_len]
            
        elif content_type == ContentType.USER_MESSAGE:
            return f"User: {content[:max_len-6]}..."
            
        elif content_type == ContentType.ASSISTANT_MESSAGE:
            return f"Assistant: {content[:max_len-11]}..."
            
        return content[:max_len]
    
    def expand_reference(self, ref_id: str) -> Optional[str]:
        """
        Expand a reference to get full content.
        
        Args:
            ref_id: The reference ID to expand
            
        Returns:
            Full content if found, None otherwise
        """
        content = self.content_store.get(ref_id)
        if content:
            logger.info(f"Expanded reference {ref_id}: {len(content)} chars")
        else:
            logger.warning(f"Reference {ref_id} not found in content store")
        return content
    
    def get_reference_info(self, ref_id: str) -> Optional[ContentReference]:
        """Get metadata about a reference."""
        return self.references.get(ref_id)
    
    async def _summarize_with_llm(self, content: str, context: str = "") -> str:
        """
        Use the lightweight LLM to summarize content, or fall back to local rules.
        
        NOTE: This is an INTERNAL call that does NOT affect the main conversation.
        - Uses separate distillation LLM (not the user's conversation LLM)
        - Response is NOT added to conversation state
        - Does NOT go through main LLM logger
        - Tracks its own usage stats
        """
        # If using local rules mode, use smart truncation instead of LLM
        if self.use_local_rules or self.llm_client is None:
            return self._local_rules_summarize(content, context)
        
        try:
            from llm_clients import Message as LLMMessage
            from datetime import datetime
            
            # Verify client is functional before attempting call
            if not hasattr(self.llm_client, 'chat'):
                logger.warning("[DISTILLATION] LLM client has no chat method, falling back to local rules")
                return self._local_rules_summarize(content, context)
            
            prompt = f"""Summarize this content concisely. Preserve ALL critical data:
- IDs, UUIDs, keys (CRITICAL for tool follow-ups)
- Names of people, places, events
- Counts, dates, numeric values
- Success/error status
- Key findings

{f"Context: {context}" if context else ""}

Content to summarize ({len(content)} chars):
{content[:4000]}

Provide a concise summary (2-4 sentences):"""

            logger.debug(f"[DISTILLATION] Summarizing {len(content)} chars (internal, not logged to conversation)")
            response = await self.llm_client.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                tools=[],
            )
            
            # Track usage
            if response.usage:
                model = self.llm_client.config.model if hasattr(self.llm_client, 'config') else "unknown"
                provider = self.llm_client.config.provider.value if hasattr(self.llm_client, 'config') else "unknown"
                pricing = self._get_pricing(model)
                input_tokens = response.usage.get("input_tokens", 0)
                output_tokens = response.usage.get("output_tokens", 0)
                cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
                
                self.usage_records.append({
                    "timestamp": datetime.now().isoformat(),
                    "model": model,
                    "provider": provider,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "type": "summarize"
                })
                
                # Persist to ledger if callback provided
                if self.usage_callback and self.thread_id:
                    try:
                        self.usage_callback(
                            thread_id=self.thread_id,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            model_provider=provider,
                            model_name=model,
                        )
                    except Exception as e:
                        logger.warning(f"[DISTILLATION] Failed to persist usage: {e}")
            
            if response.content:
                logger.debug(f"[DISTILLATION] Summary: {len(response.content)} chars")
                return response.content.strip()
            return self._local_rules_summarize(content, context)
            
        except Exception as e:
            logger.warning(f"[DISTILLATION] LLM summarization failed: {e}")
            return self._local_rules_summarize(content, context)
    
    def _local_rules_summarize(self, content: str, context: str = "") -> str:
        """
        Rule-based summarization without LLM.
        
        Extracts key patterns:
        - UUIDs (critical for tool follow-ups)
        - Counts and numeric values
        - Names and identifiers
        - Success/error status
        """
        import re
        
        if len(content) < self.config.summarize_threshold:
            return content
        
        preserved_parts = []
        
        # Extract UUIDs
        uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', content, re.I)
        if uuids:
            unique_uuids = list(dict.fromkeys(uuids))[:8]
            preserved_parts.append(f"IDs: {', '.join(unique_uuids)}")
        
        # Extract counts
        count_patterns = re.findall(r'(?:"count":\s*(\d+)|returned\s+(\d+)\s+rows?|(\d+)\s+(?:results?|items?|records?|rows?))', content, re.I)
        if count_patterns:
            counts = [c for group in count_patterns for c in group if c]
            if counts:
                preserved_parts.append(f"Counts: {', '.join(counts[:5])}")
        
        # Extract names
        names = re.findall(r'"(?:canonical_name|name|title)":\s*"([^"]+)"', content)
        if names:
            unique_names = list(dict.fromkeys(names))[:6]
            preserved_parts.append(f"Names: {', '.join(unique_names)}")
        
        # Check success/error
        if '"success": true' in content.lower() or '"success":true' in content.lower():
            preserved_parts.append("Status: success")
        elif '"error"' in content.lower():
            error_match = re.search(r'"error":\s*"([^"]{1,80})', content)
            if error_match:
                preserved_parts.append(f"Error: {error_match.group(1)}")
        
        # Build summary
        header = f"[Local summary of {len(content)} chars]"
        if preserved_parts:
            key_info = " | ".join(preserved_parts)
            preview = content[:600].strip()
            return f"{header}\nKey info: {key_info}\nPreview: {preview}..."
        else:
            return content[:self.config.summarize_threshold] + f"\n... [truncated {len(content) - self.config.summarize_threshold} chars]"
    
    def _get_pricing(self, model: str) -> dict:
        """Get pricing for a model (per 1M tokens). 
        Source: https://platform.openai.com/docs/pricing (Jan 2026)"""
        pricing_map = {
            "gpt-5-nano": {"input": 0.05, "output": 0.40},
            "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
            "gpt-5-mini": {"input": 0.25, "output": 2.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        }
        return pricing_map.get(model, {"input": 0.10, "output": 0.50})
    
    async def _summarize_turn(
        self, 
        turn_messages: list[dict],
        turn_number: int
    ) -> str:
        """Summarize a complete turn (user message + assistant response + tools)."""
        try:
            from llm_clients import Message as LLMMessage
            
            # Build turn description
            turn_desc = []
            for msg in turn_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")[:500]
                
                if role == "user":
                    turn_desc.append(f"User asked: {content}")
                elif role == "assistant":
                    if msg.get("tool_calls"):
                        tools = [tc.get("name", "?") for tc in msg["tool_calls"]]
                        turn_desc.append(f"Assistant used tools: {', '.join(tools)}")
                    if content:
                        turn_desc.append(f"Assistant said: {content[:200]}")
                elif role == "tool":
                    tool_id = msg.get("tool_call_id", "")[:8]
                    turn_desc.append(f"Tool result ({tool_id}): {content[:100]}")
            
            turn_text = "\n".join(turn_desc)
            
            prompt = f"""Summarize this conversation turn in 1-2 sentences.
Preserve: what was asked, what tools were used, what was found/done.

Turn {turn_number}:
{turn_text}

Summary:"""

            # Use local rules if configured
            if self.use_local_rules or self.llm_client is None:
                summary = f"Turn {turn_number}: {turn_desc[0][:100] if turn_desc else 'No content'}"
                if len(turn_desc) > 1:
                    summary += f" → {turn_desc[-1][:100]}"
                return summary

            logger.debug(f"[DISTILLATION] Summarizing turn {turn_number} (internal)")
            response = await self.llm_client.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                tools=[],
            )
            
            # Track usage
            if response.usage:
                model = self.llm_client.config.model if hasattr(self.llm_client, 'config') else "unknown"
                pricing = self._get_pricing(model)
                input_tokens = response.usage.get("input_tokens", 0)
                output_tokens = response.usage.get("output_tokens", 0)
                cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
                
                self.usage_records.append({
                    "timestamp": datetime.now().isoformat(),
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "type": "turn_summary"
                })
            
            if response.content:
                logger.debug(f"[DISTILLATION] Turn {turn_number} summary: {response.content[:100]}...")
                return response.content.strip()
            return f"Turn {turn_number}: {turn_desc[0] if turn_desc else 'No content'}"
            
        except Exception as e:
            logger.warning(f"[DISTILLATION] Turn summarization failed: {e}")
            return f"Turn {turn_number}: [summarization failed]"
    
    async def _update_cumulative_summary(self, new_turn_summaries: list[str]) -> str:
        """Update the cumulative distilled summary with new turn summaries."""
        if not new_turn_summaries:
            return self.distilled_summary
            
        try:
            from llm_clients import Message as LLMMessage
            
            new_content = "\n".join(new_turn_summaries)
            
            if not self.distilled_summary:
                # First distillation
                self.distilled_summary = new_content
                return self.distilled_summary
            
            prompt = f"""Merge these conversation summaries into a cohesive summary.
Keep the most important information. Max {self.config.max_summary_chars} chars.

Previous summary:
{self.distilled_summary}

New turns to incorporate:
{new_content}

Merged summary:"""

            # Use local rules if configured
            if self.use_local_rules or self.llm_client is None:
                # Simple merge: keep recent content, truncate old
                combined = f"{self.distilled_summary}\n\n{new_content}"
                self.distilled_summary = combined[-self.config.max_summary_chars:]
                return self.distilled_summary

            response = await self.llm_client.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                tools=[],
            )
            
            # Track usage
            if response.usage:
                model = self.llm_client.config.model if hasattr(self.llm_client, 'config') else "unknown"
                pricing = self._get_pricing(model)
                input_tokens = response.usage.get("input_tokens", 0)
                output_tokens = response.usage.get("output_tokens", 0)
                cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
                
                self.usage_records.append({
                    "timestamp": datetime.now().isoformat(),
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "type": "cumulative_summary"
                })
            
            if response.content:
                self.distilled_summary = response.content.strip()[:self.config.max_summary_chars]
            else:
                # Fallback: just append
                combined = f"{self.distilled_summary}\n\n{new_content}"
                self.distilled_summary = combined[:self.config.max_summary_chars]
                
            return self.distilled_summary
            
        except Exception as e:
            logger.warning(f"Summary merge failed: {e}")
            combined = f"{self.distilled_summary}\n\n{new_content}"
            self.distilled_summary = combined[:self.config.max_summary_chars]
            return self.distilled_summary
    
    async def distill(
        self,
        messages: list,  # LangChain messages
        current_turn: int,
        force_full_distill: bool = False
    ) -> DistilledContext:
        """
        Distill messages into an optimized context for the LLM.
        
        Args:
            messages: All conversation messages (LangChain format)
            current_turn: Current turn number
            force_full_distill: Force re-distillation of all content
            
        Returns:
            DistilledContext with summary, references, and recent messages
        """
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        
        # Group messages by turn
        turns: list[list[dict]] = []
        current_turn_messages: list[dict] = []
        
        for msg in messages:
            msg_dict = self._message_to_dict(msg)
            
            if isinstance(msg, HumanMessage):
                if current_turn_messages:
                    turns.append(current_turn_messages)
                current_turn_messages = [msg_dict]
            else:
                current_turn_messages.append(msg_dict)
        
        if current_turn_messages:
            turns.append(current_turn_messages)
        
        total_turns = len(turns)
        
        # Determine which turns need distillation vs keeping full
        turns_to_keep_full = self.config.recent_messages_full // 2  # Rough estimate
        distill_up_to = max(0, total_turns - turns_to_keep_full)
        
        # Distill older turns that haven't been distilled yet
        new_turn_summaries = []
        for turn_idx in range(self.last_distilled_turn, distill_up_to):
            if turn_idx < len(turns):
                turn_msgs = turns[turn_idx]
                summary = await self._summarize_turn(turn_msgs, turn_idx + 1)
                new_turn_summaries.append(summary)
                
                # Store full content as expandable references
                for msg_dict in turn_msgs:
                    self._store_message_as_reference(msg_dict, turn_idx + 1)
        
        # Update cumulative summary
        if new_turn_summaries:
            await self._update_cumulative_summary(new_turn_summaries)
            self.last_distilled_turn = distill_up_to
        
        # Build recent messages (keep in full)
        recent_messages = []
        recent_tool_count = 0
        
        for turn_idx in range(distill_up_to, total_turns):
            if turn_idx < len(turns):
                for msg_dict in turns[turn_idx]:
                    # Apply selective summarization to tool results
                    if msg_dict.get("role") == "tool":
                        content = msg_dict.get("content", "")
                        recent_tool_count += 1
                        
                        # Summarize older tool results even in recent turns
                        if (recent_tool_count > self.config.recent_tool_results_full and
                            len(content) > self.config.summarize_threshold):
                            # Store full and replace with summary
                            ref = self._store_content(
                                content,
                                ContentType.TOOL_RESULT,
                                turn_idx + 1,
                                tool_name=msg_dict.get("tool_name")
                            )
                            summary = await self._summarize_with_llm(
                                content, 
                                f"Tool result from {msg_dict.get('tool_name', 'unknown')}"
                            )
                            msg_dict = {
                                **msg_dict,
                                "content": f"[Summarized, ref:{ref.ref_id}]\n{summary}"
                            }
                    
                    recent_messages.append(msg_dict)
        
        # Build reference index for distilled content
        reference_index = [
            ref for ref in self.references.values()
            if ref.turn_number <= distill_up_to
        ]
        reference_index.sort(key=lambda r: r.turn_number)
        
        # Calculate stats
        total_original = sum(len(self.content_store.get(r.ref_id, "")) for r in reference_index)
        total_original += sum(len(m.get("content", "")) for m in recent_messages)
        
        total_distilled = len(self.distilled_summary)
        total_distilled += sum(len(r.brief) for r in reference_index)
        total_distilled += sum(len(m.get("content", "")) for m in recent_messages)
        
        context = DistilledContext(
            distilled_summary=self.distilled_summary,
            reference_index=reference_index,
            recent_messages=recent_messages,
            available_refs=set(self.content_store.keys()),
            total_original_chars=total_original,
            total_distilled_chars=total_distilled
        )
        
        logger.info(
            f"Distilled context: {len(turns)} turns, "
            f"{len(reference_index)} refs, "
            f"{len(recent_messages)} recent msgs, "
            f"compression: {context.get_compression_ratio():.2f}"
        )
        
        return context
    
    def _message_to_dict(self, msg) -> dict:
        """Convert a LangChain message to a dict."""
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        
        if isinstance(msg, HumanMessage):
            return {"role": "user", "content": msg.content}
        elif isinstance(msg, AIMessage):
            result = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                result["tool_calls"] = msg.tool_calls
            return result
        elif isinstance(msg, ToolMessage):
            return {
                "role": "tool",
                "content": msg.content,
                "tool_call_id": msg.tool_call_id,
                "tool_name": msg.name if hasattr(msg, 'name') else None
            }
        return {"role": "unknown", "content": str(msg)}
    
    def _store_message_as_reference(self, msg_dict: dict, turn_number: int) -> Optional[ContentReference]:
        """Store a message as an expandable reference."""
        role = msg_dict.get("role", "")
        content = msg_dict.get("content", "")
        
        if not content or len(content) < 100:
            return None  # Don't store tiny content
        
        content_type = {
            "user": ContentType.USER_MESSAGE,
            "assistant": ContentType.ASSISTANT_MESSAGE,
            "tool": ContentType.TOOL_RESULT
        }.get(role, ContentType.ASSISTANT_MESSAGE)
        
        return self._store_content(
            content,
            content_type,
            turn_number,
            tool_name=msg_dict.get("tool_name")
        )
    
    def build_context_prompt(self, context: DistilledContext) -> str:
        """
        Build a context prompt that includes the distilled summary and reference index.
        
        This should be prepended to the conversation for the LLM.
        """
        parts = []
        
        if context.distilled_summary:
            parts.append(f"## Earlier Conversation Summary\n{context.distilled_summary}")
        
        if context.reference_index and self.config.include_reference_index:
            ref_lines = []
            for ref in context.reference_index[-20:]:  # Last 20 refs
                ref_lines.append(f"- [{ref.ref_id}] Turn {ref.turn_number}: {ref.brief}")
            
            parts.append(
                f"## Available References (use expand_reference tool to get full content)\n" +
                "\n".join(ref_lines)
            )
        
        return "\n\n".join(parts)
    
    def reset(self):
        """Reset the distillation state (for new conversations)."""
        self.content_store.clear()
        self.references.clear()
        self.distilled_summary = ""
        self.last_distilled_turn = 0
        logger.info("Distillation state reset")


# Singleton instance
_distillation_helper: Optional[DistillationHelper] = None


def get_distillation_helper() -> DistillationHelper:
    """Get or create the singleton distillation helper."""
    global _distillation_helper
    
    if _distillation_helper is None:
        from config import DISTILLATION_LLM_CONFIG
        from llm_clients import create_llm_client
        
        llm_client = create_llm_client(DISTILLATION_LLM_CONFIG)
        _distillation_helper = DistillationHelper(llm_client)
        logger.info(f"Created DistillationHelper with {DISTILLATION_LLM_CONFIG.model}")
    
    return _distillation_helper


def reset_distillation_helper():
    """Reset the singleton (for testing or new sessions)."""
    global _distillation_helper
    if _distillation_helper:
        _distillation_helper.reset()
    _distillation_helper = None
