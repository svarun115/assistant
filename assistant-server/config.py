"""
Configuration and defaults for the Journal Agent Orchestrator.

This module defines default MCP servers and supported LLM providers.
Modify DEFAULT_MCP_SERVERS to match your local setup.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class LLMProvider(Enum):
    """Supported LLM providers."""
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"
    MOCK = "mock"


class MCPTransport(Enum):
    """MCP server transport types."""
    STDIO = "stdio"      # Local process via stdin/stdout
    HTTP = "http"        # Remote HTTP+SSE server
    STREAMABLE_HTTP = "streamable_http"  # Newer streamable HTTP transport


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server.
    
    For STDIO (local):
        MCPServerConfig(
            name="journal-db",
            transport=MCPTransport.STDIO,
            command="node",
            args=["dist/index.js"],
            env={"DATABASE_URL": "..."}
        )
    
    For HTTP (remote):
        MCPServerConfig(
            name="journal-db",
            transport=MCPTransport.HTTP,
            url="http://localhost:3001/mcp",
            headers={"Authorization": "Bearer ..."}
        )
    """
    name: str
    transport: MCPTransport = MCPTransport.STDIO
    
    # STDIO transport options
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    
    # HTTP transport options
    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    
    # Common options
    enabled: bool = True
    description: str = ""
    
    def __post_init__(self):
        """Validate configuration based on transport type."""
        if self.transport == MCPTransport.STDIO:
            if not self.command:
                raise ValueError(f"STDIO transport requires 'command' for server: {self.name}")
        elif self.transport in (MCPTransport.HTTP, MCPTransport.STREAMABLE_HTTP):
            if not self.url:
                raise ValueError(f"HTTP transport requires 'url' for server: {self.name}")


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None  # For Ollama or custom endpoints
    temperature: float = 0.7
    max_tokens: int = 4096


# Default MCP server configurations
# Matches VS Code mcp.json configuration
DEFAULT_MCP_SERVERS: list[MCPServerConfig] = [
    MCPServerConfig(
        name="journal-db",
        transport=MCPTransport.HTTP,
        url="http://localhost:3333/mcp",
        description="Personal journal database with events, people, locations, workouts, meals"
    ),
    MCPServerConfig(
        name="garmin",
        transport=MCPTransport.HTTP,
        url="http://localhost:5555/mcp",
        description="Garmin Connect fitness data - activities, sleep, body metrics"
    ),
    MCPServerConfig(
        name="gmail",
        transport=MCPTransport.HTTP,
        url="http://localhost:3001/mcp",
        description="Gmail access for transaction receipts and confirmations"
    ),
    MCPServerConfig(
        name="splitwise",
        transport=MCPTransport.HTTP,
        url="http://localhost:2222/mcp",
        description="Splitwise expense tracking and splitting"
    ),
    MCPServerConfig(
        name="google-places",
        transport=MCPTransport.HTTP,
        url="http://localhost:1111/mcp",
        description="Google Places API for location lookup and place_id resolution"
    ),
]


# Default LLM configurations
DEFAULT_LLM_CONFIGS: dict[LLMProvider, LLMConfig] = {
    LLMProvider.CLAUDE: LLMConfig(
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-4-20250514",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    ),
    LLMProvider.OPENAI: LLMConfig(
        provider=LLMProvider.OPENAI,
        model="gpt-5-nano",
        api_key=os.getenv("OPENAI_API_KEY"),
        max_tokens=16384,  # Increased for GPT-5 Nano's larger capacity
    ),
    LLMProvider.OLLAMA: LLMConfig(
        provider=LLMProvider.OLLAMA,
        model="llama3.2",
        base_url="http://localhost:11434",
    ),
}


# Dedicated lightweight LLM for distillation/summarization tasks
# Uses a cheap, fast model to summarize tool results without affecting main conversation
# Options: "gpt-5-nano", "gpt-4o-mini", "local-rules" (rule-based, no LLM)
DISTILLATION_LLM_CONFIG = LLMConfig(
    provider=LLMProvider.OPENAI,
    model="gpt-5-nano",  # Cheapest option - $0.05/M input, $0.40/M output
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.3,  # Lower temperature for more consistent summaries
    max_tokens=1024,  # Summaries don't need many tokens
)

# Available distillation models for UI picker
# For summarization tasks, we optimize for cost over capability
# Actual pricing from https://platform.openai.com/docs/pricing (Jan 2026)
DISTILLATION_MODELS = [
    {
        "id": "gpt-5-nano",
        "name": "GPT-5 Nano",
        "description": "Cheapest ($0.05/$0.40 per 1M tokens)",
        "provider": "openai",
        "model": "gpt-5-nano",
        "pricing": {"input": 0.05, "output": 0.40}
    },
    {
        "id": "gpt-4o-mini",
        "name": "GPT-4o Mini",
        "description": "Better quality (~2x cost, $0.15/$0.60 per 1M)",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "pricing": {"input": 0.15, "output": 0.60}
    },
    {
        "id": "local-rules",
        "name": "Local Rules",
        "description": "Free - regex-based extraction, no LLM",
        "provider": "local",
        "model": "rules",
        "pricing": {"input": 0, "output": 0}
    },
]


def get_default_llm_config(provider: LLMProvider) -> LLMConfig:
    """Get default configuration for an LLM provider."""
    return DEFAULT_LLM_CONFIGS.get(provider, DEFAULT_LLM_CONFIGS[LLMProvider.OPENAI])


def get_enabled_mcp_servers() -> list[MCPServerConfig]:
    """Get list of enabled MCP servers."""
    return [s for s in DEFAULT_MCP_SERVERS if s.enabled]
