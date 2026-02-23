"""
LLM Client Abstraction Layer.

Provides a unified interface for different LLM providers.
Each client handles the provider-specific API format and tool calling.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from config import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents an LLM's request to call a tool."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None  # For tool results


@dataclass 
class LLMResponse:
    """Response from an LLM."""
    content: str
    tool_calls: list[ToolCall]
    stop_reason: str  # "end_turn", "tool_use", "max_tokens"
    usage: dict[str, int]  # {"input_tokens": X, "output_tokens": Y}


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the client connection."""
        pass
    
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """
        Send a chat request to the LLM.
        
        Args:
            messages: Conversation history
            tools: Available tools in provider-specific format
            system_prompt: Optional system prompt
            
        Returns:
            LLM response with content and/or tool calls
        """
        pass
    
    @abstractmethod
    def format_tool_result(self, tool_call_id: str, result: str) -> Message:
        """Format a tool result for the conversation."""
        pass
    
    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ):
        """
        Stream a chat response from the LLM.
        
        Yields partial content strings as they arrive.
        Returns the final LLMResponse when complete.
        
        Default implementation falls back to non-streaming.
        """
        response = await self.chat(messages, tools, system_prompt)
        yield {"type": "content", "content": response.content}
        yield {"type": "done", "response": response}


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic's Claude API."""
    
    async def initialize(self) -> None:
        try:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.config.api_key)
        except ImportError:
            raise ImportError("anthropic package required. Install with: pip install anthropic")
    
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            if msg.role == "tool":
                # Tool results in Anthropic format
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content
                    }]
                })
            elif msg.tool_calls:
                # Assistant message with tool calls
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments
                    })
                anthropic_messages.append({"role": "assistant", "content": content})
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Make API call
        response = await self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system_prompt or "",
            messages=anthropic_messages,
            tools=tools if tools else None
        )
        
        # Parse response
        content = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input
                ))
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason="tool_use" if response.stop_reason == "tool_use" else "end_turn",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }
        )
    
    def format_tool_result(self, tool_call_id: str, result: str) -> Message:
        return Message(
            role="tool",
            content=result,
            tool_call_id=tool_call_id
        )


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI's API."""
    
    async def initialize(self) -> None:
        try:
            from openai import AsyncOpenAI
            # Configure with higher retry limits for rate limiting
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                max_retries=5,  # Retry up to 5 times on rate limits
                timeout=120.0,  # 2 minute timeout
            )
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
    
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        # Convert messages to OpenAI format
        openai_messages = []
        
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        
        for msg in messages:
            if msg.role == "tool":
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id
                })
            elif msg.tool_calls:
                openai_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })
            else:
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Make API call
        kwargs = {
            "model": self.config.model,
            "messages": openai_messages,
            "tools": tools if tools else None
        }
        
        # GPT-5 models use max_completion_tokens instead of max_tokens
        if "gpt-5" in self.config.model.lower():
            kwargs["max_completion_tokens"] = self.config.max_tokens
        else:
            kwargs["max_tokens"] = self.config.max_tokens
            
        response = await self._client.chat.completions.create(**kwargs)
        
        # Parse response
        choice = response.choices[0]
        message = choice.message
        
        # Debug logging for GPT-5 models
        logger.info(f"OpenAI response: finish_reason={choice.finish_reason}, content_len={len(message.content or '')}")
        if hasattr(response.usage, 'completion_tokens_details') and response.usage.completion_tokens_details:
            details = response.usage.completion_tokens_details
            logger.info(f"Token details: reasoning={getattr(details, 'reasoning_tokens', 0)}, "
                       f"accepted_prediction={getattr(details, 'accepted_prediction_tokens', 0)}, "
                       f"rejected_prediction={getattr(details, 'rejected_prediction_tokens', 0)}")
        
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))
        
        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            stop_reason="tool_use" if choice.finish_reason == "tool_calls" else "end_turn",
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens
            }
        )
    
    def format_tool_result(self, tool_call_id: str, result: str) -> Message:
        return Message(
            role="tool",
            content=result,
            tool_call_id=tool_call_id
        )
    
    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ):
        """Stream chat response from OpenAI."""
        # Convert messages to OpenAI format
        openai_messages = []
        
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        
        for msg in messages:
            if msg.role == "tool":
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id
                })
            elif msg.tool_calls:
                openai_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })
            else:
                openai_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Make streaming API call
        kwargs = {
            "model": self.config.model,
            "messages": openai_messages,
            "tools": tools if tools else None,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        
        # GPT-5 models use max_completion_tokens
        if "gpt-5" in self.config.model.lower():
            kwargs["max_completion_tokens"] = self.config.max_tokens
        else:
            kwargs["max_tokens"] = self.config.max_tokens
        
        # Accumulate response
        content = ""
        tool_calls = []
        tool_call_args = {}  # id -> accumulated args string
        finish_reason = None
        usage = {"input_tokens": 0, "output_tokens": 0}
        
        async for chunk in await self._client.chat.completions.create(**kwargs):
            # Handle usage in final chunk
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = {
                    "input_tokens": chunk.usage.prompt_tokens,
                    "output_tokens": chunk.usage.completion_tokens
                }
            
            if not chunk.choices:
                continue
                
            delta = chunk.choices[0].delta
            
            # Accumulate content
            if delta.content:
                content += delta.content
                yield {"type": "content", "content": delta.content}
            
            # Accumulate tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.id:
                        # New tool call
                        tool_call_args[tc.id] = ""
                        tool_calls.append({
                            "id": tc.id,
                            "name": tc.function.name if tc.function else "",
                            "arguments": ""
                        })
                    if tc.function and tc.function.arguments:
                        # Find the tool call to update
                        for existing_tc in tool_calls:
                            if existing_tc["id"] == tc.id or (not tc.id and existing_tc == tool_calls[-1]):
                                existing_tc["arguments"] += tc.function.arguments
                                break
            
            # Capture finish reason
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
        
        # Debug logging for streaming
        logger.info(f"OpenAI stream complete: finish_reason={finish_reason}, content_len={len(content)}, "
                   f"tool_calls={len(tool_calls)}, usage={usage}")
        
        # Build final tool calls
        final_tool_calls = []
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            final_tool_calls.append(ToolCall(
                id=tc["id"],
                name=tc["name"],
                arguments=args
            ))
        
        # Yield final response
        response = LLMResponse(
            content=content,
            tool_calls=final_tool_calls,
            stop_reason="tool_use" if finish_reason == "tool_calls" else "end_turn",
            usage=usage
        )
        yield {"type": "done", "response": response}


class OllamaClient(BaseLLMClient):
    """Client for Ollama (local LLMs)."""
    
    async def initialize(self) -> None:
        try:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url or "http://localhost:11434",
                timeout=120.0
            )
        except ImportError:
            raise ImportError("httpx package required. Install with: pip install httpx")
    
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        # Convert messages to Ollama format
        ollama_messages = []
        
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})
        
        for msg in messages:
            if msg.role == "tool":
                # Ollama tool results
                ollama_messages.append({
                    "role": "tool",
                    "content": msg.content
                })
            else:
                ollama_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Make API call
        payload = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature
            }
        }
        
        if tools:
            payload["tools"] = tools
        
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Parse response
        message = data.get("message", {})
        tool_calls = []
        
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{len(tool_calls)}"),
                    name=func.get("name", ""),
                    arguments=func.get("arguments", {})
                ))
        
        return LLMResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            stop_reason="tool_use" if tool_calls else "end_turn",
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0)
            }
        )
    
    def format_tool_result(self, tool_call_id: str, result: str) -> Message:
        return Message(
            role="tool",
            content=result,
            tool_call_id=tool_call_id
        )
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM client for testing frontend-backend integration.
    
    Returns Lorem Ipsum-like responses and invokes read-only tools
    from available MCP servers to test the full flow.
    """
    
    LOREM_RESPONSES = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
        "Curabitur pretium tincidunt lacus. Nulla gravida orci a odio. Nullam varius, turpis et commodo pharetra.",
    ]
    
    # Read-only tools to invoke for testing (by server)
    # Note: Tool names come directly from MCP servers without prefix
    MOCK_TOOL_CALLS = {
        "google-places": [
            {"name": "get_elevation", "args": {"locations": [{"lat": 37.4224764, "lng": -122.0842499}]}},
        ],
        "journal-db": [
            {"name": "get_database_schema", "args": {}},
            {"name": "execute_sql_query", "args": {"query": "SELECT COUNT(*) as count FROM events WHERE deleted_at IS NULL LIMIT 1"}},
            {"name": "get_domain_instructions", "args": {"domain": "events"}},
        ],
        "garmin": [
            {"name": "get_user_summary", "args": {"date": "2025-12-31"}},
        ],
        "gmail": [
            {"name": "search_emails", "args": {"query": "receipt", "max_results": 1}},
        ],
        "splitwise": [
            # Splitwise doesn't have obvious read-only tools, skip
        ],
    }
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._call_count = 0
        self._turn_count = 0
    
    async def initialize(self) -> None:
        """No initialization needed for mock client."""
        logger.info("Mock LLM client initialized")
    
    def _mock_distillation(self, prompt: str) -> LLMResponse:
        """
        Rule-based distillation for mock testing.
        
        Extracts key words from conversation to simulate summarization:
        - First 5 words from last 3 messages
        - First word from older messages
        - Appends mock context info
        """
        import re
        
        # Parse the conversation from the prompt
        lines = prompt.split("\n")
        user_lines = []
        assistant_lines = []
        
        for line in lines:
            if line.startswith("User:"):
                user_lines.append(line[5:].strip())
            elif line.startswith("Assistant:"):
                assistant_lines.append(line[10:].strip())
        
        summary_parts = []
        
        # Process user messages
        all_messages = user_lines + assistant_lines
        n_recent = min(3, len(all_messages))
        
        # First 5 words from last 3 messages
        for msg in all_messages[-n_recent:]:
            words = msg.split()[:5]
            if words:
                summary_parts.append(" ".join(words) + "...")
        
        # First word from older messages
        older_messages = all_messages[:-n_recent] if len(all_messages) > n_recent else []
        first_words = [msg.split()[0] for msg in older_messages if msg.split()]
        if first_words:
            summary_parts.append(f"Earlier: {', '.join(first_words[:5])}")
        
        # Add mock context
        summary_parts.append(f"[Turn {self._turn_count}, {len(user_lines)} user msgs]")
        
        summary = " | ".join(summary_parts) if summary_parts else "Mock distillation - no content to summarize."
        
        return LLMResponse(
            content=summary,
            tool_calls=[],
            stop_reason="end_turn",
            usage={"input_tokens": 50, "output_tokens": 30}
        )
    
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        import random
        import uuid
        
        self._call_count += 1
        
        # Check if this is a distillation request
        last_message = messages[-1] if messages else None
        if last_message and "Summarize this conversation" in last_message.content:
            return self._mock_distillation(last_message.content)
        
        # Get available tool names - handle both Anthropic and OpenAI formats
        available_tools = {}
        for t in tools:
            # Anthropic format: {"name": "...", ...}
            # OpenAI format: {"type": "function", "function": {"name": "...", ...}}
            if "function" in t:
                name = t["function"].get("name", "")
            else:
                name = t.get("name", "")
            if name:
                available_tools[name] = t
        
        logger.info(f"MockLLM: {len(available_tools)} tools available: {list(available_tools.keys())[:10]}...")
        
        # On first call of a turn, make some tool calls
        # Check if last message is a tool result
        is_continuing_tool_flow = messages and messages[-1].role == "tool"
        
        if not is_continuing_tool_flow:
            self._turn_count += 1
            
            # Build tool calls from available tools
            tool_calls = []
            call_id = 0
            
            for server, server_tools in self.MOCK_TOOL_CALLS.items():
                for tool_spec in server_tools:
                    tool_name = tool_spec["name"]
                    # Check if tool is available (try both with and without mcp_ prefix)
                    if tool_name in available_tools:
                        tool_calls.append(ToolCall(
                            id=f"mock_{uuid.uuid4().hex[:8]}",
                            name=tool_name,
                            arguments=tool_spec["args"]
                        ))
                        call_id += 1
                        if call_id >= 3:  # Limit to 3 tools per turn
                            break
                if call_id >= 3:
                    break
            
            logger.info(f"MockLLM: Built {len(tool_calls)} tool calls from {len(available_tools)} available tools")
            
            if tool_calls:
                return LLMResponse(
                    content="Let me look up some information for you...",
                    tool_calls=tool_calls,
                    stop_reason="tool_use",
                    usage={"input_tokens": 150, "output_tokens": 50}
                )
        
        # After tools or if no tools available, return Lorem Ipsum
        response_text = random.choice(self.LOREM_RESPONSES)
        
        # Add some context about what was done
        if is_continuing_tool_flow:
            tool_results_count = sum(1 for m in messages if m.role == "tool")
            response_text = f"Based on the {tool_results_count} tool calls I made, here's my analysis:\n\n{response_text}\n\n**Note:** This is a mock response for testing. Turn #{self._turn_count}, Call #{self._call_count}."
        else:
            response_text = f"**Mock Response:**\n\n{response_text}\n\n*This is a test response from the mock LLM.*"
        
        return LLMResponse(
            content=response_text,
            tool_calls=[],
            stop_reason="end_turn",
            usage={
                "input_tokens": random.randint(100, 500),
                "output_tokens": random.randint(50, 200)
            }
        )
    
    def format_tool_result(self, tool_call_id: str, result: str) -> Message:
        return Message(
            role="tool",
            content=result,
            tool_call_id=tool_call_id
        )


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """
    Factory function to create appropriate LLM client.
    
    Args:
        config: LLM configuration
        
    Returns:
        Initialized LLM client
    """
    clients = {
        LLMProvider.CLAUDE: AnthropicClient,
        LLMProvider.OPENAI: OpenAIClient,
        LLMProvider.OLLAMA: OllamaClient,
        LLMProvider.MOCK: MockLLMClient,
    }
    
    client_class = clients.get(config.provider)
    if not client_class:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")
    
    return client_class(config)
