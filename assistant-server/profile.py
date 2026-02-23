"""
AssistantProfile — single source of truth for all assistant configuration.

Nothing in the gateway hardcodes URLs, paths, or credentials.
Every component receives a profile and reads its config from it.

Profile hierarchy:
    personal  — personal MCP servers, varun_journal DB, personal skills
    work      — work MCP servers, work_journal DB, work skills  (stub, future)

Usage:
    profile = build_personal_profile()   # reads env vars, applies defaults
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import LLMConfig, LLMProvider, MCPServerConfig, MCPTransport

logger = logging.getLogger(__name__)


@dataclass
class AssistantProfile:
    """
    All configuration for one assistant instance (personal, work, etc.).

    Rule: every component receives profile: AssistantProfile and reads
    all config from it. Nothing hardcodes DB URLs, MCP addresses, or paths.

    Multi-user affordances (single user today, filter later):
      - user_id on every assistant_system row
      - auth middleware returns Profile (single key→profile today, JWT tomorrow)
      - profile-relative paths only (no Path.home() scattered across codebase)
    """

    # Identity
    name: str                                       # "personal", "work"
    user_id: str                                    # "varun" — row-level isolation key

    # Tool servers
    mcp_servers: list[MCPServerConfig]

    # State databases
    # Phase 1:  SQLite file paths (e.g., "journal_checkpoints.db")
    # Phase 1b: PostgreSQL DSNs  (e.g., "postgresql://...@.../assistant_system")
    checkpoint_db: str                              # LangGraph checkpoint storage
    threads_db: str                                 # Thread metadata storage

    # Future PostgreSQL DSNs (None until Phase 1b)
    system_db_url: Optional[str] = None             # assistant_system (infra, shared)
    journal_db_url: Optional[str] = None            # varun_journal (personal data)

    # File paths
    skills_dir: Optional[Path] = None              # skills/ directory
    data_dir: Optional[Path] = None                # user-context.md + daily-context.json

    # LLM defaults (user can override at runtime via UI model picker)
    default_llm: Optional[LLMConfig] = None

    # Auth — gateway API key. None = no auth (local dev only).
    api_key: Optional[str] = None

    # Skills access control. None = all skills allowed.
    allowed_skills: Optional[list[str]] = None


def _resolve_skills_dir() -> Optional[Path]:
    """Find the skills directory from standard candidate locations."""
    candidates = [
        Path(__file__).parent / "skills",
        Path("skills"),
        Path("agent-orchestrator/skills"),
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return None


def build_personal_profile() -> AssistantProfile:
    """
    Build the personal assistant profile from environment variables.

    All values have sensible local-dev defaults so the server starts
    without any env config. Override via .env or docker-compose env_file
    for production.

    Key env vars:
        LLM_PROVIDER        — "claude" (default), "openai", "ollama"
        LLM_MODEL           — model name (default: claude-sonnet-4-6)
        ANTHROPIC_API_KEY   — required for Claude
        OPENAI_API_KEY      — required for OpenAI
        OLLAMA_BASE_URL     — Ollama server URL (default: http://localhost:11434)

        ASSISTANT_API_KEY   — gateway auth key (None = no auth, local dev default)

        DATA_DIR            — path to user-context.md + daily-context.json
                              (default: ~/.claude/data)

        MCP_JOURNAL_URL     — journal DB MCP  (default: http://localhost:3333/mcp)
        MCP_GARMIN_URL      — garmin MCP      (default: http://localhost:5555/mcp)
        MCP_GOOGLE_URL      — google-workspace (default: http://localhost:3000/mcp)
        MCP_PLACES_URL      — google-places   (default: http://localhost:1111/mcp)
        MCP_SPLITWISE_URL   — splitwise MCP   (default: http://localhost:4000/mcp)

        JOURNAL_DB_URL      — postgresql DSN for varun_journal (used by db-mcp-server)
        SYSTEM_DB_URL       — postgresql DSN for assistant_system (Phase 1b+)
        CHECKPOINT_DB       — SQLite path for LangGraph checkpoints (Phase 1 only)
        THREADS_DB          — SQLite path for thread metadata (Phase 1 only)
    """
    # --- LLM ---
    provider_str = os.getenv("LLM_PROVIDER", "claude").lower()
    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        logger.warning(f"Unknown LLM_PROVIDER '{provider_str}', falling back to claude")
        provider = LLMProvider.CLAUDE

    model_defaults = {
        LLMProvider.CLAUDE: "claude-sonnet-4-6",
        LLMProvider.OPENAI: "gpt-5-nano",
        LLMProvider.OLLAMA: "qwen2.5:72b",
    }
    model = os.getenv("LLM_MODEL", model_defaults.get(provider, "claude-sonnet-4-6"))

    api_key_by_provider = {
        LLMProvider.CLAUDE: os.getenv("ANTHROPIC_API_KEY"),
        LLMProvider.OPENAI: os.getenv("OPENAI_API_KEY"),
        LLMProvider.OLLAMA: None,
    }
    base_url = (
        os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        if provider == LLMProvider.OLLAMA
        else None
    )
    default_llm = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key_by_provider.get(provider),
        base_url=base_url,
    )

    # --- MCP servers ---
    mcp_servers = [
        MCPServerConfig(
            name="journal-db",
            transport=MCPTransport.HTTP,
            url=os.getenv("MCP_JOURNAL_URL", "http://localhost:3333/mcp"),
            description="Personal journal database",
        ),
        MCPServerConfig(
            name="garmin",
            transport=MCPTransport.HTTP,
            url=os.getenv("MCP_GARMIN_URL", "http://localhost:5555/mcp"),
            description="Garmin fitness data",
        ),
        MCPServerConfig(
            name="google-workspace",
            transport=MCPTransport.HTTP,
            url=os.getenv("MCP_GOOGLE_URL", "http://localhost:3000/mcp"),
            description="Google Calendar, Tasks, Gmail, Sheets",
        ),
        MCPServerConfig(
            name="google-places",
            transport=MCPTransport.HTTP,
            url=os.getenv("MCP_PLACES_URL", "http://localhost:1111/mcp"),
            description="Google Places API",
        ),
        MCPServerConfig(
            name="splitwise",
            transport=MCPTransport.HTTP,
            url=os.getenv("MCP_SPLITWISE_URL", "http://localhost:4000/mcp"),
            description="Splitwise expense tracking",
        ),
    ]

    # --- Paths ---
    data_dir_env = os.getenv("DATA_DIR")
    data_dir = Path(data_dir_env) if data_dir_env else Path.home() / ".claude" / "data"

    skills_dir = _resolve_skills_dir()
    if skills_dir:
        logger.info(f"Skills directory resolved: {skills_dir}")
    else:
        logger.warning("Skills directory not found — skills will be unavailable")

    return AssistantProfile(
        name="personal",
        user_id="varun",
        mcp_servers=mcp_servers,
        checkpoint_db=os.getenv("CHECKPOINT_DB", "journal_checkpoints.db"),
        threads_db=os.getenv("THREADS_DB", "journal_threads_meta.db"),
        system_db_url=os.getenv("SYSTEM_DB_URL"),
        journal_db_url=os.getenv("JOURNAL_DB_URL"),
        skills_dir=skills_dir,
        data_dir=data_dir,
        default_llm=default_llm,
        api_key=os.getenv("ASSISTANT_API_KEY"),
        allowed_skills=None,  # All skills allowed for personal profile
    )
