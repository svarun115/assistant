"""
Web Server using LangGraph-based Journal Agent.

This replaces the original web_server.py with LangGraph integration.
Key changes:
1. Uses JournalGraph instead of JournalAgent
2. Uses ThreadManager instead of JournalChatManager
3. State is automatically persisted via LangGraph checkpointer
4. Thread metadata is tracked in ThreadManager

To use, rename this file to web_server.py or import from it.
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional

# Import LangGraph components
from graph import create_journal_graph, create_journal_graph_persistent, create_journal_graph_postgres, ThreadManager, JournalGraph
from graph.state import JournalState, SessionMode

# Import existing components we still need
from config import LLMConfig, LLMProvider
from profile import AssistantProfile, build_personal_profile
from llm_clients import create_llm_client
from bridge_manager import BridgeManager
from mcp_bridge import MCPToolBridge
from skeleton import TimelineSkeletonBuilder
from skills import SkillsLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_last_turn_usage(state: Optional[dict], model_name: str = None) -> dict:
    """Get usage from the last turn's LLM calls, including cost."""
    if not state:
        return {"input_tokens": 0, "output_tokens": 0, "cost": 0}
    
    usage_records = state.get("usage_records", [])
    if not usage_records:
        return {"input_tokens": 0, "output_tokens": 0, "cost": 0}
    
    # Get the last usage record (most recent LLM call this turn)
    last_record = usage_records[-1]
    
    input_tokens = last_record.get("input_tokens", 0)
    output_tokens = last_record.get("output_tokens", 0)
    
    # Calculate cost server-side
    cost = calculate_cost(input_tokens, output_tokens, model_name or "unknown")
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    }


# --- Pricing Data (single source of truth for cost calculations) ---
# Prices are per million tokens

MODEL_PRICING = {
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "mock-default": {"input": 0, "output": 0},
}


def calculate_cost(input_tokens: int, output_tokens: int, model_name: str) -> float:
    """Calculate cost in dollars for given token counts and model."""
    pricing = MODEL_PRICING.get(model_name, {"input": 0, "output": 0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


# --- FastAPI App ---

app = FastAPI(title="Journal Agent API (LangGraph)", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    API key authentication middleware.

    Two modes:
      1. DB-backed (production):  SYSTEM_DB_URL is set → hash key, lookup in api_keys table.
         Attaches user_id, profile_name, allow_operator_llm to request.state.
      2. Local dev fallback:  No SYSTEM_DB_URL → string-compare against ASSISTANT_API_KEY env var.
         If no key configured at all, all requests pass through (local dev, no auth).

    Accepted via:
      - Header:      X-API-Key: <key>
      - Query param: ?api_key=<key>  (for WebSocket connections)

    Excluded paths (no auth required):
      - /static/*   — UI assets
      - /api/health — uptime checks
    """

    EXCLUDED_PREFIXES = ("/static",)
    EXCLUDED_PATHS = ("/api/health",)

    async def dispatch(self, request: Request, call_next):
        # Skip auth if no key is configured (local dev, no ASSISTANT_API_KEY)
        if not _profile or not _profile.api_key:
            # No auth configured — set defaults for downstream code
            request.state.user_id = _profile.user_id if _profile else "varun"
            request.state.profile_name = _profile.name if _profile else "personal"
            request.state.allow_operator_llm = True
            return await call_next(request)

        path = request.url.path
        if path in self.EXCLUDED_PATHS or any(path.startswith(p) for p in self.EXCLUDED_PREFIXES):
            return await call_next(request)

        key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if not key:
            return Response(content="Unauthorized", status_code=401)

        # --- DB-backed auth (production) ---
        if _auth_pool:
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            try:
                async with _auth_pool.connection() as conn:
                    row = await conn.execute(
                        "SELECT user_id, profile_name, allow_operator_llm "
                        "FROM api_keys WHERE key_hash = %s AND is_revoked = FALSE",
                        (key_hash,),
                    )
                    result = await row.fetchone()
                    if not result:
                        return Response(content="Unauthorized", status_code=401)
                    request.state.user_id = result[0]
                    request.state.profile_name = result[1]
                    request.state.allow_operator_llm = result[2]
                    # Update last_used asynchronously (fire and forget)
                    await conn.execute(
                        "UPDATE api_keys SET last_used = NOW() WHERE key_hash = %s",
                        (key_hash,),
                    )
            except Exception as e:
                logger.error(f"api_keys DB lookup failed: {e}")
                return Response(content="Internal Server Error", status_code=500)
        else:
            # --- Local dev fallback: string-compare against ASSISTANT_API_KEY ---
            if key != _profile.api_key:
                return Response(content="Unauthorized", status_code=401)
            request.state.user_id = _profile.user_id
            request.state.profile_name = _profile.name
            request.state.allow_operator_llm = True

        return await call_next(request)


app.add_middleware(APIKeyMiddleware)

# --- Global State ---

_profile: Optional[AssistantProfile] = None
_auth_pool = None  # psycopg AsyncConnectionPool for api_keys lookups (set when SYSTEM_DB_URL is configured)
_credential_store = None  # CredentialStore instance (set when SYSTEM_DB_URL + encryption key are configured)
_bridge_manager: Optional[BridgeManager] = None  # Per-user MCP bridge lifecycle
_agent_loader = None         # AgentLoader — resolves agent definitions from DB
_notification_queue = None   # NotificationQueue — agent → COS delivery
_scheduler = None            # AgentScheduler — cron-based background agents
_spawner = None              # AgentSpawner — task / background / foreground agents
_graph: Optional[JournalGraph] = None
_thread_manager: Optional[ThreadManager] = None
_current_thread_id: Optional[str] = None
_llm_config: Optional[LLMConfig] = None
_last_debug_info: dict = {}
_init_lock = asyncio.Lock()


# --- Request/Response Models ---

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None  # Format: "provider/model"
    thread_id: Optional[str] = None


class ModelSelectRequest(BaseModel):
    provider: str
    model: str


class NewThreadRequest(BaseModel):
    title: Optional[str] = "New Conversation"


class UpdateThreadRequest(BaseModel):
    title: Optional[str] = None
    emoji: Optional[str] = None


# --- Initialization ---

async def get_or_create_graph(
    provider: str = None,
    model: str = None,
    mcp_bridge: Optional[MCPToolBridge] = None,
    user_id: Optional[str] = None,
    allow_operator_llm: bool = True,
) -> JournalGraph:
    """
    Get or create the LangGraph-based journal agent with persistent storage.

    Args:
        provider: LLM provider name (e.g. "claude", "openai"). Falls back to profile default.
        model: Model name (e.g. "claude-sonnet-4-6"). Falls back to profile default.
        mcp_bridge: Per-user MCPToolBridge from BridgeManager. If None, gets one for the
                     default profile user (backward compat for startup / model-switch calls).
        user_id: User ID for BYOK key lookup. Falls back to profile default.
        allow_operator_llm: Whether this user is approved for operator LLM key fallback.
    """
    global _graph, _llm_config, _profile

    # Apply profile defaults for any unspecified args
    default_llm = _profile.default_llm if _profile else None
    effective_provider = provider or (default_llm.provider.value if default_llm else "claude")
    effective_model = model or (default_llm.model if default_llm else "claude-sonnet-4-6")
    effective_user = user_id or (_profile.user_id if _profile else "varun")

    logger.info(f"get_or_create_graph called: provider={effective_provider}, model={effective_model}, user={effective_user}")

    async with _init_lock:
        # Check if we need to recreate for different model
        target_provider = LLMProvider(effective_provider)
        if _graph and _llm_config:
            if _llm_config.provider == target_provider and _llm_config.model == effective_model:
                return _graph
            logger.info(f"Switching model from {_llm_config.provider}/{_llm_config.model} to {effective_provider}/{effective_model}")
            await _graph.cleanup()

        # --- BYOK: resolve API key ---
        # Priority: 1) user's own key from CredentialStore  2) operator key (if allowed)  3) reject
        #
        # Service names in user_credentials are provider-agnostic company names:
        #   LLMProvider.CLAUDE  → "llm_anthropic"
        #   LLMProvider.OPENAI  → "llm_openai"
        # Users can store keys for both providers simultaneously and the right one
        # is selected based on which provider is being used for this session.
        _BYOK_SERVICE = {
            LLMProvider.CLAUDE: "llm_anthropic",
            LLMProvider.OPENAI: "llm_openai",
        }
        byok_service = _BYOK_SERVICE.get(target_provider)
        api_key = None

        # 1) Check CredentialStore for user's own key (for this provider)
        if _credential_store and byok_service:
            try:
                byok_data = await _credential_store.get(effective_user, byok_service)
                if byok_data and byok_data.get("api_key"):
                    api_key = byok_data["api_key"]
                    # User may also specify a preferred model for this provider
                    if byok_data.get("preferred_model") and not provider:
                        effective_model = byok_data["preferred_model"]
                    logger.info(f"BYOK: using {effective_user}'s own {byok_service} key")
            except Exception as e:
                logger.warning(f"BYOK lookup failed for {effective_user}/{byok_service}: {e}")

        # 2) Fall back to operator key (if allowed)
        if not api_key:
            if not allow_operator_llm:
                raise HTTPException(
                    status_code=403,
                    detail="No LLM key configured. Provide your own key or request operator access.",
                )
            # Operator key from profile/env
            if default_llm and default_llm.provider == target_provider:
                api_key = default_llm.api_key
            elif target_provider == LLMProvider.OPENAI:
                api_key = os.getenv("OPENAI_API_KEY")
            elif target_provider == LLMProvider.CLAUDE:
                api_key = os.getenv("ANTHROPIC_API_KEY")
            else:
                api_key = None

        # Set max_tokens based on model (GPT-5 models need more for reasoning tokens)
        max_tokens = 4096  # default
        if "gpt-5" in effective_model.lower():
            max_tokens = 16384
        elif "claude" in effective_model.lower():
            max_tokens = 8192

        _llm_config = LLMConfig(
            provider=target_provider,
            model=effective_model,
            api_key=api_key,
            max_tokens=max_tokens,
        )
        logger.info(f"Created LLMConfig: provider={target_provider}, model={effective_model}, api_key_set={api_key is not None}")
        llm_client = create_llm_client(_llm_config)
        logger.info(f"Created LLM client: {type(llm_client).__name__}")
        await llm_client.initialize()

        # Get MCP bridge — use provided per-user bridge, or get default user's bridge from manager
        bridge = mcp_bridge
        if not bridge and _bridge_manager:
            default_user = _profile.user_id if _profile else "varun"
            bridge = await _bridge_manager.get_bridge(default_user)
        if not bridge:
            raise RuntimeError("No MCP bridge available — BridgeManager not initialized")

        # Create skeleton builder and skills loader (with profile paths)
        skeleton_builder = TimelineSkeletonBuilder(bridge)
        skills_loader = SkillsLoader(
            skills_dir=_profile.skills_dir if _profile else None,
            data_dir=_profile.data_dir if _profile else None,
        )

        # Create graph — PostgreSQL when SYSTEM_DB_URL is set, SQLite otherwise
        system_db_url = _profile.system_db_url if _profile else None
        if system_db_url:
            _graph = await create_journal_graph_postgres(pg_dsn=system_db_url)
            storage_label = "PostgreSQL (assistant_system)"
        else:
            checkpoint_db = _profile.checkpoint_db if _profile else "journal_checkpoints.db"
            _graph = await create_journal_graph_persistent(db_path=checkpoint_db)
            storage_label = f"SQLite ({checkpoint_db})"

        _graph.configure(
            mcp_bridge=bridge,
            llm_client=llm_client,
            skeleton_builder=skeleton_builder,
            skills_loader=skills_loader,
        )

        logger.info(f"LangGraph agent created with {effective_provider}/{effective_model} (storage: {storage_label})")

    return _graph


@app.on_event("startup")
async def startup():
    """Initialize graph and thread manager on startup."""
    global _profile, _auth_pool, _credential_store, _bridge_manager, \
           _agent_loader, _notification_queue, _scheduler, _spawner, \
           _thread_manager, _current_thread_id

    try:
        # Build profile — single source of truth for all config
        _profile = build_personal_profile()
        logger.info(f"Loaded profile: {_profile.name} (user_id={_profile.user_id})")

        # Initialize auth pool for api_keys lookups (production only)
        if _profile.system_db_url:
            try:
                from psycopg_pool import AsyncConnectionPool
                _auth_pool = AsyncConnectionPool(
                    conninfo=_profile.system_db_url,
                    min_size=1,
                    max_size=3,
                    open=False,
                )
                await _auth_pool.open()
                logger.info("Auth pool opened (api_keys DB lookups enabled)")
            except Exception as e:
                logger.warning(f"Failed to open auth pool — falling back to env key auth: {e}")
                _auth_pool = None

        # Initialize CredentialStore (production only — needs auth pool)
        if _auth_pool:
            try:
                from credential_store import CredentialStore
                _credential_store = CredentialStore(_auth_pool)
                logger.info("CredentialStore initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize CredentialStore: {e}")
                _credential_store = None

        # Initialize BridgeManager (per-user MCP bridge lifecycle)
        _bridge_manager = BridgeManager(
            base_servers=_profile.mcp_servers,
            credential_store=_credential_store,
        )
        logger.info("BridgeManager initialized")

        # --- Phase 2/2.5: Agent infrastructure ---

        if _auth_pool:
            # AgentLoader — all-DB agent definition system.
            # Templates are seeded ONCE during deployment setup via:
            #   python migrations/run_seed_agent_templates.py
            # Runtime reads from DB only — no filesystem scanning at startup.
            from agent_loader import AgentLoader
            _agent_loader = AgentLoader(_auth_pool)
            logger.info("AgentLoader initialized (DB-backed)")

            # Notification queue
            from notification_queue import NotificationQueue
            _notification_queue = NotificationQueue(_auth_pool)
            logger.info("NotificationQueue initialized")

        # AgentSpawner — wires together graph factory, bridge, thread manager, notif queue
        if _notification_queue:
            from agent_spawner import AgentSpawner
            _spawner = AgentSpawner(
                graph_factory=get_or_create_graph,
                bridge_manager=_bridge_manager,
                agent_loader=_agent_loader,
                thread_manager=None,  # set below after ThreadManager is created
                notification_queue=_notification_queue,
                default_user_id=_profile.user_id,
            )

        # Scheduler — starts background polling loop
        if _auth_pool and _spawner:
            from scheduler import AgentScheduler
            _scheduler = AgentScheduler(
                pg_pool=_auth_pool,
                on_due_agent=_spawner.spawn_background,
            )
            # Sync schedules from all installed agent instances' HEARTBEAT declarations
            if _agent_loader:
                await _scheduler.sync_from_heartbeats(_agent_loader, _profile.user_id)
            await _scheduler.start()
            logger.info("AgentScheduler started")

        # Initialize thread manager using profile's threads DB
        _thread_manager = ThreadManager(_profile.threads_db)

        # Back-wire thread_manager into spawner (created before ThreadManager above)
        if _spawner:
            _spawner._thread_manager = _thread_manager

        # Wire up distillation usage callback to use the same ledger
        from graph.nodes import set_distillation_usage_callback
        set_distillation_usage_callback(_thread_manager.record_usage)
        
        # Try to resume the most recent thread with messages
        recent_thread = _thread_manager.get_most_recent_thread(with_messages_only=True)
        if recent_thread:
            _current_thread_id = recent_thread.thread_id
            logger.info(f"Resuming thread: {_current_thread_id} - {recent_thread.title}")
            
            # If thread has a model, switch to it
            if recent_thread.model_provider and recent_thread.model_name:
                await get_or_create_graph(recent_thread.model_provider, recent_thread.model_name)
                logger.info(f"Switched to thread's model: {recent_thread.model_provider}/{recent_thread.model_name}")
            else:
                await get_or_create_graph()
        else:
            # No threads with messages, create a new one with current model
            model_provider = _llm_config.provider.value if _llm_config else "mock"
            model_name = _llm_config.model if _llm_config else "mock-default"
            _current_thread_id = _thread_manager.create_thread(
                "New Conversation",
                model_provider=model_provider,
                model_name=model_name
            )
            logger.info(f"Created new thread: {_current_thread_id}")
            await get_or_create_graph()
        
    except Exception as e:
        logger.error(f"Failed to initialize on startup: {e}")


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    global _bridge_manager, _graph, _auth_pool, _scheduler

    # Stop scheduler first — prevents new agents from firing during shutdown
    if _scheduler:
        try:
            await _scheduler.stop()
        except Exception as e:
            logger.warning(f"Error stopping scheduler: {e}")
        _scheduler = None

    # Clean up graph (async checkpointer)
    if _graph:
        try:
            await _graph.cleanup()
        except Exception as e:
            logger.warning(f"Error during graph cleanup: {e}")
        _graph = None

    if _bridge_manager:
        try:
            await _bridge_manager.cleanup()
        except Exception as e:
            logger.warning(f"Error during bridge manager cleanup: {e}")
        _bridge_manager = None

    if _auth_pool:
        try:
            await _auth_pool.close()
        except Exception as e:
            logger.warning(f"Error closing auth pool: {e}")
        _auth_pool = None


async def _get_default_bridge() -> Optional[MCPToolBridge]:
    """Get the default user's bridge (for endpoints that don't have request context)."""
    if not _bridge_manager:
        return None
    user_id = _profile.user_id if _profile else "varun"
    try:
        return await _bridge_manager.get_bridge(user_id)
    except Exception:
        return None


# --- API Endpoints ---

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "graph_ready": _graph is not None,
        "current_thread": _current_thread_id,
    }


@app.get("/api/tools")
async def get_tools():
    """Get available MCP tools grouped by server."""
    bridge = await _get_default_bridge()
    if not bridge:
        return {"servers": []}

    servers = {}
    for tool in bridge._tools.values():
        server_name = tool.server_name
        if server_name not in servers:
            conn = bridge._connections.get(server_name)
            servers[server_name] = {
                "name": server_name,
                "transport": conn.transport_type.value if conn else "unknown",
                "tools": [],
                "resources": []
            }
        servers[server_name]["tools"].append({
            "name": tool.name,
            "description": tool.description[:200] + "..." if len(tool.description) > 200 else tool.description,
        })

    return {"servers": list(servers.values())}


@app.get("/api/tool/{server}/{tool_name}")
async def get_tool_detail(server: str, tool_name: str):
    """Get detailed information about a specific tool."""
    bridge = await _get_default_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="MCP bridge not initialized")

    # Find the tool - try both with and without server prefix
    tool = bridge._tools.get(tool_name)

    # Also try prefixed name pattern (e.g., mcp_journal_db_tool_name)
    if not tool:
        prefixed_name = f"mcp_{server.replace('-', '_')}_{tool_name}"
        tool = bridge._tools.get(prefixed_name)

    if not tool or tool.server_name != server:
        # Search through all tools for this server
        for t in bridge._tools.values():
            if t.server_name == server and (t.name == tool_name or t.name.endswith(f"_{tool_name}")):
                tool = t
                break
    
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found on server '{server}'")
    
    return {
        "name": tool.name,
        "server": tool.server_name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
    }


@app.get("/api/models")
async def get_models():
    """Get available LLM models with pricing info."""
    return {
        "models": [
            {
                "provider": "openai", 
                "name": "GPT 5 Nano", 
                "model": "gpt-5-nano",
                "pricing": MODEL_PRICING.get("gpt-5-nano", {"input": 0, "output": 0})
            },
            {
                "provider": "openai", 
                "name": "GPT 4o Mini", 
                "model": "gpt-4o-mini",
                "pricing": MODEL_PRICING.get("gpt-4o-mini", {"input": 0, "output": 0})
            },
            {
                "provider": "mock", 
                "name": "Mock", 
                "model": "mock-default",
                "pricing": MODEL_PRICING.get("mock-default", {"input": 0, "output": 0})
            },
        ],
        "current": {
            "provider": _llm_config.provider.value if _llm_config else "openai",
            "model": _llm_config.model if _llm_config else "gpt-5-nano"
        }
    }


@app.post("/api/model")
async def set_model(request: ModelSelectRequest):
    """Change the current model. Also updates current thread's model if it has no messages."""
    try:
        await get_or_create_graph(request.provider, request.model)
        
        # If current thread has no messages yet, update its model binding
        if _thread_manager and _current_thread_id:
            metadata = _thread_manager.get_thread(_current_thread_id)
            if metadata and metadata.message_count == 0:
                _thread_manager.update_thread(
                    _current_thread_id,
                    model_provider=request.provider,
                    model_name=request.model
                )
                logger.info(f"Updated thread {_current_thread_id} model to {request.provider}/{request.model}")
        
        return {"status": "ok", "provider": request.provider, "model": request.model}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Distillation Model Endpoints ===

@app.get("/api/distillation/models")
async def get_distillation_models():
    """Get available distillation models with pricing info."""
    from config import DISTILLATION_MODELS
    from graph.nodes import get_thread_distiller
    
    # Get current distiller's model info
    current_model = "gpt-5-nano"  # default
    mode = "llm"
    
    if _current_thread_id:
        distiller = get_thread_distiller(_current_thread_id)
        if distiller:
            info = distiller.get_current_model()
            current_model = info.get("model", "gpt-5-nano")
            mode = info.get("mode", "llm")
    
    return {
        "models": DISTILLATION_MODELS,
        "current": {"model": current_model, "mode": mode}
    }


class DistillationModelRequest(BaseModel):
    model: str


@app.post("/api/distillation/model")
async def set_distillation_model(request: DistillationModelRequest):
    """Change the distillation model for the current thread."""
    from graph.nodes import get_thread_distiller
    
    if not _current_thread_id:
        raise HTTPException(status_code=400, detail="No active thread")
    
    distiller = get_thread_distiller(_current_thread_id)
    if not distiller:
        raise HTTPException(status_code=400, detail="No distiller for current thread")
    
    result = await distiller.set_model(request.model)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to change model"))
    
    return result


@app.get("/api/distillation/usage")
async def get_distillation_usage(model: Optional[str] = None):
    """Get distillation usage stats, optionally filtered by model.
    
    If model is specified, queries from the persistent ledger.
    Otherwise, returns current session stats from in-memory helper.
    """
    from graph.nodes import get_thread_distiller
    
    # If model specified, query from ledger for persistent stats
    if model and _thread_manager:
        return _thread_manager.get_distillation_usage_by_model(model)
    
    # Fallback to in-memory session stats
    if not _current_thread_id:
        return {"input_tokens": 0, "output_tokens": 0, "cost": 0, "calls": 0, "model": "none"}
    
    distiller = get_thread_distiller(_current_thread_id)
    if not distiller:
        return {"input_tokens": 0, "output_tokens": 0, "cost": 0, "calls": 0, "model": "none"}
    
    return distiller.get_usage_stats()


@app.get("/api/session")
async def get_session():
    """Get current session state from LangGraph."""
    if not _graph or not _current_thread_id:
        return {"mode": "idle", "target_date": None, "turn_count": 0, "thread_state": "", "distilled_summary": ""}
    
    state = await _graph.get_state(_current_thread_id)
    if not state:
        return {"mode": "idle", "target_date": None, "turn_count": 0, "thread_state": "", "distilled_summary": ""}
    
    # Build thread state summary from state fields
    state_parts = []
    
    # Add turn count
    turn_count = state.get("turn_count", 0)
    state_parts.append(f"🔄 Turns: {turn_count}")
    
    # Add target date if set
    target_date = state.get("target_date")
    if target_date:
        state_parts.append(f"📅 Discussing: {target_date}")
    
    # Add pending items count
    pending_entities = len(state.get("pending_entities", []))
    pending_events = len(state.get("pending_events", []))
    if pending_entities > 0 or pending_events > 0:
        state_parts.append(f"📝 Pending: {pending_events} events, {pending_entities} entities")
    
    # Add skeleton status
    if state.get("skeleton"):
        state_parts.append("🗓️ Timeline skeleton loaded")
    
    return {
        "mode": state.get("mode", "idle"),
        "target_date": state.get("target_date"),
        "turn_count": turn_count,
        "has_skeleton": state.get("skeleton") is not None,
        "pending_entities": pending_entities,
        "pending_events": pending_events,
        "total_tokens": state.get("total_input_tokens", 0) + state.get("total_output_tokens", 0),
        "thread_state": "\n".join(state_parts) if state_parts else "",
        "distilled_summary": state.get("distilled_summary", ""),
    }


@app.get("/api/threads/{thread_id}/logs")
async def get_thread_logs(thread_id: str, limit: int = 50):
    """Get LLM request/response logs for a thread."""
    from llm_logger import get_llm_logger
    llm_logger = get_llm_logger()
    logs = llm_logger.get_logs(thread_id, limit=limit)
    return {"logs": logs, "thread_id": thread_id}


@app.delete("/api/threads/{thread_id}/logs")
async def clear_thread_logs(thread_id: str):
    """Clear LLM logs for a thread."""
    from llm_logger import get_llm_logger
    llm_logger = get_llm_logger()
    success = llm_logger.clear_logs(thread_id)
    return {"success": success, "thread_id": thread_id}


@app.get("/api/skeleton")
async def get_skeleton():
    """Get current timeline skeleton."""
    if not _graph or not _current_thread_id:
        return {"skeleton": None}
    
    state = await _graph.get_state(_current_thread_id)
    if state and state.get("skeleton"):
        return {"skeleton": state["skeleton"].get("summary", "")}
    return {"skeleton": None}


@app.get("/api/history")
async def get_history():
    """Get conversation history for current thread.
    
    Merges consecutive tool_execution messages into a single entry
    to avoid cluttering the UI with separate messages for each tool call iteration.
    """
    if not _graph or not _current_thread_id:
        return {"history": []}
    
    messages = await _graph.get_messages(_current_thread_id)
    
    history = []
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history.append({
                "role": "user",
                "content": msg.content,
                "type": "message",
            })
        elif isinstance(msg, AIMessage):
            # Skip completely empty messages
            if not msg.content and not msg.tool_calls:
                continue
            
            if msg.tool_calls:
                # Determine type: "thinking" if has content, "tool_execution" if just tools
                tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
                has_content = msg.content and msg.content.strip()
                msg_type = "thinking" if has_content else "tool_execution"
                
                # Bug #6 fix: Merge consecutive tool_execution messages
                if (msg_type == "tool_execution" and 
                    history and 
                    history[-1].get("type") == "tool_execution" and
                    history[-1].get("role") == "assistant"):
                    # Merge tool calls into the previous tool_execution entry
                    history[-1]["tool_calls"].extend(tool_names)
                else:
                    history.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "type": msg_type,
                        "tool_calls": tool_names,
                    })
            else:
                # Skip empty response messages
                if not msg.content or not msg.content.strip():
                    continue
                # Final response message
                history.append({
                    "role": "assistant",
                    "content": msg.content,
                    "type": "response",
                })
    
    return {"history": history}


# --- Thread Management Endpoints ---

@app.get("/api/threads")
async def list_threads(limit: int = 50):
    """List all conversation threads."""
    if not _thread_manager:
        return {"threads": [], "current_thread_id": None}
    
    threads = _thread_manager.list_threads(limit)
    return {
        "threads": [t.to_dict() for t in threads],
        "current_thread_id": _current_thread_id,
        "total_count": _thread_manager.get_thread_count(),
    }


@app.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get a specific thread with metadata and messages."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    metadata = _thread_manager.get_thread(thread_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Get messages from graph
    messages = []
    if _graph:
        msgs = await _graph.get_messages(thread_id)
        from langchain_core.messages import HumanMessage, AIMessage
        for msg in msgs:
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                messages.append({"role": "assistant", "content": msg.content})
    
    return {
        **metadata.to_dict(),
        "messages": messages,
    }


@app.post("/api/threads")
async def create_thread(request: NewThreadRequest):
    """Create a new conversation thread with the current model."""
    global _current_thread_id
    
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    # Get current model info
    model_provider = _llm_config.provider.value if _llm_config else "mock"
    model_name = _llm_config.model if _llm_config else "mock-default"
    
    # Create new thread tied to current model
    thread_id = _thread_manager.create_thread(
        request.title or "New Conversation",
        model_provider=model_provider,
        model_name=model_name
    )
    _current_thread_id = thread_id
    
    return {
        "thread_id": thread_id,
        "title": request.title,
        "created_at": datetime.now().isoformat(),
        "model_provider": model_provider,
        "model_name": model_name,
    }


@app.post("/api/threads/{thread_id}/load")
async def load_thread(thread_id: str):
    """Load and switch to a specific thread, switching to thread's model."""
    global _current_thread_id
    
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    # Verify thread exists
    metadata = _thread_manager.get_thread(thread_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    _current_thread_id = thread_id
    
    # Switch to thread's model if it has one
    if metadata.model_provider and metadata.model_name:
        await get_or_create_graph(metadata.model_provider, metadata.model_name)
    
    # Get messages and state
    messages = []
    graph_state = None
    if _graph:
        msgs = await _graph.get_messages(thread_id)
        from langchain_core.messages import HumanMessage, AIMessage
        for msg in msgs:
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content, "type": "message"})
            elif isinstance(msg, AIMessage):
                # Skip completely empty messages
                if not msg.content and not msg.tool_calls:
                    continue
                
                if msg.tool_calls:
                    # Determine type: "thinking" if has content, "tool_execution" if just tools
                    tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
                    has_content = msg.content and msg.content.strip()
                    msg_type = "thinking" if has_content else "tool_execution"
                    
                    # Bug #6 fix: Merge consecutive tool_execution messages
                    if (msg_type == "tool_execution" and 
                        messages and 
                        messages[-1].get("type") == "tool_execution" and
                        messages[-1].get("role") == "assistant"):
                        # Merge tool calls into the previous tool_execution entry
                        messages[-1]["tool_calls"].extend(tool_names)
                    else:
                        messages.append({
                            "role": "assistant",
                            "content": msg.content or "",
                            "type": msg_type,
                            "tool_calls": tool_names,
                        })
                else:
                    # Skip empty response messages
                    if not msg.content or not msg.content.strip():
                        continue
                    # Final response
                    messages.append({"role": "assistant", "content": msg.content, "type": "response"})
        
        # Get graph state for this thread
        graph_state = await _graph.get_state(thread_id)
    
    # Build session info from state
    session = {}
    if graph_state:
        # Build thread_state display
        state_parts = []
        turn_count = graph_state.get("turn_count", 0)
        state_parts.append(f"🔄 Turns: {turn_count}")
        
        mode = graph_state.get("mode", "idle")
        mode_display = {"idle": "💤 Idle", "logging": "📝 Logging", "querying": "🔍 Querying"}.get(mode, f"⚡ {mode}")
        state_parts.append(mode_display)
        
        target_date = graph_state.get("target_date")
        if target_date:
            state_parts.append(f"📅 Date: {target_date}")
        
        msgs = graph_state.get("messages", [])
        user_msgs = sum(1 for m in msgs if hasattr(m, 'type') and m.type == 'human')
        ai_msgs = sum(1 for m in msgs if hasattr(m, 'type') and m.type == 'ai')
        state_parts.append(f"💬 Messages: {user_msgs} user, {ai_msgs} assistant")
        
        # Build context summary
        context_parts = []
        distilled = graph_state.get("distilled_summary", "")
        if distilled:
            context_parts.append(f"📝 Distilled History:\n{distilled}")
        else:
            if msgs:
                recent_count = min(len(msgs), 6)
                context_parts.append(f"💬 Recent: Last {recent_count} messages in context")
        
        skills = graph_state.get("skills_content", "")
        if skills:
            skill_count = skills.count("##")
            context_parts.append(f"📚 Skills: {skill_count} domain sections loaded")
        
        if not context_parts:
            context_parts.append("Base system prompt only")
        
        session = {
            "mode": mode,
            "target_date": target_date,
            "turn_count": turn_count,
            "thread_state": "\n".join(state_parts),
            "distilled_summary": "\n".join(context_parts),
        }
    
    return {
        **metadata.to_dict(),
        "messages": messages,
        "session": session,
    }


@app.patch("/api/threads/{thread_id}")
async def update_thread(thread_id: str, request: UpdateThreadRequest):
    """Update thread metadata."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    success = _thread_manager.update_thread(thread_id, title=request.title, emoji=request.emoji)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update thread")
    
    return {"status": "updated", "thread_id": thread_id}


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread (soft delete)."""
    global _current_thread_id
    
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    success = _thread_manager.delete_thread(thread_id)
    if not success:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # If we deleted current thread, create a new one
    if _current_thread_id == thread_id:
        _current_thread_id = _thread_manager.create_thread("New Conversation")
    
    return {"status": "deleted", "thread_id": thread_id}


@app.get("/api/threads/search/{query}")
async def search_threads(query: str, limit: int = 20):
    """Search threads by title."""
    if not _thread_manager:
        return {"threads": []}
    
    threads = _thread_manager.search_threads(query, limit)
    return {"threads": [t.to_dict() for t in threads]}


@app.post("/api/clear")
async def clear_conversation():
    """Clear current conversation by creating new thread."""
    global _current_thread_id
    
    if _thread_manager:
        _current_thread_id = _thread_manager.create_thread("New Conversation")
    
    return {"status": "cleared", "thread_id": _current_thread_id}


@app.get("/api/debug")
async def get_debug_info():
    """Get debug information for the debug panel."""
    session = await get_session()
    skeleton = await get_skeleton()
    
    # Get usage info
    usage = {}
    if _thread_manager:
        usage = _thread_manager.get_total_usage()
    
    return {
        "session": session,
        "skeleton": skeleton.get("skeleton"),
        "usage": usage,
        "last_tool_calls": _last_debug_info.get("last_tool_calls", []),
        "model": {
            "provider": _llm_config.provider.value if _llm_config else "claude",
            "model": _llm_config.model if _llm_config else "unknown",
        },
        "tools_count": len(_graph._mcp_bridge.tool_names) if _graph and _graph._mcp_bridge else 0,
    }


@app.get("/api/usage")
async def get_usage(filter: str = "all", thread_id: str = None, model: str = None):
    """Get token usage statistics with optional filtering.
    
    All cost calculations happen server-side. Frontend just displays.
    
    Args:
        filter: One of 'thread', 'day', 'week', 'month', 'all'
        thread_id: Thread ID (for filter='thread', defaults to current thread)
        model: Optional model name filter (e.g., 'gpt-5-nano')
    
    Returns:
        {
            "input_tokens": int,
            "output_tokens": int,
            "cost": float,  # Pre-calculated cost in dollars
            "calls": int,   # Number of API calls (messages for thread, messages total for ranges)
            "filter": str,
            "model": str or null,
            "by_model": {...}  # Breakdown by model (for time range filters)
        }
    """
    if not _thread_manager:
        return {"input_tokens": 0, "output_tokens": 0, "cost": 0, "calls": 0, "filter": filter}
    
    from datetime import datetime, timedelta
    
    if filter == "thread":
        # Get usage for specific thread, optionally filtered by model
        tid = thread_id or _current_thread_id
        if tid:
            if model:
                # Query ledger for this thread + model combination
                result = _thread_manager.get_thread_usage_by_model(tid, model)
                cost = calculate_cost(
                    result["input_tokens"],
                    result["output_tokens"],
                    model
                )
                return {
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "cost": cost,
                    "calls": result["call_count"],
                    "filter": "thread",
                    "thread_id": tid,
                    "model": model,
                }
            else:
                # No model filter - return thread totals
                metadata = _thread_manager.get_thread(tid)
                if metadata:
                    model_name = metadata.model_name or "unknown"
                    cost = calculate_cost(
                        metadata.total_input_tokens,
                        metadata.total_output_tokens,
                        model_name
                    )
                    return {
                        "input_tokens": metadata.total_input_tokens,
                        "output_tokens": metadata.total_output_tokens,
                        "cost": cost,
                        "calls": metadata.message_count,
                        "filter": "thread",
                        "thread_id": tid,
                        "model": model_name,
                    }
        return {"input_tokens": 0, "output_tokens": 0, "cost": 0, "calls": 0, "filter": "thread"}
    
    # Calculate date range based on filter
    now = datetime.now()
    if filter == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif filter == "month":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # "all"
        start = datetime(2020, 1, 1)  # Far enough back
    
    end = now + timedelta(days=1)  # Include today
    
    result = _thread_manager.get_usage_by_date_range(
        start.isoformat(),
        end.isoformat(),
        model_name=model  # Optional model filter
    )
    
    # Calculate total cost from by_model breakdown
    total_cost = 0
    by_model_with_cost = {}
    for model_name, usage in result.get("by_model", {}).items():
        model_cost = calculate_cost(
            usage["input_tokens"],
            usage["output_tokens"],
            model_name
        )
        total_cost += model_cost
        by_model_with_cost[model_name] = {
            **usage,
            "cost": model_cost,
        }
    
    return {
        "input_tokens": result.get("total_input_tokens", 0),
        "output_tokens": result.get("total_output_tokens", 0),
        "cost": total_cost,
        "calls": result.get("message_count", 0),
        "filter": filter,
        "model": model,
        "by_model": by_model_with_cost,
    }


@app.get("/api/tool-usage")
async def get_tool_usage(thread_id: str = None):
    """Get tool usage statistics for a thread.
    
    Args:
        thread_id: Thread ID (defaults to current thread)
    
    Returns:
        {
            "tools": {"tool_name": count, ...},
            "total_calls": int
        }
    """
    from llm_logger import get_llm_logger
    
    tid = thread_id or _current_thread_id
    if not tid:
        return {"tools": {}, "total_calls": 0}
    
    llm_logger = get_llm_logger()
    return llm_logger.get_tool_usage(tid)


# --- Chat Endpoint ---

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Send a chat message and get response."""
    global _last_debug_info, _current_thread_id
    
    # Get or create graph with specified model
    if request.model:
        if "/" in request.model:
            provider, model = request.model.split("/", 1)
        else:
            provider = "claude"
            model = request.model
        graph = await get_or_create_graph(provider, model)
    else:
        graph = await get_or_create_graph()
    
    # Use specified thread or current
    thread_id = request.thread_id or _current_thread_id
    if not thread_id:
        thread_id = _thread_manager.create_thread("New Conversation")
        _current_thread_id = thread_id
    
    # Increment message count immediately when user sends a message
    # This ensures the thread persists in history even if LLM fails
    if _thread_manager:
        current_metadata = _thread_manager.get_thread(thread_id)
        if current_metadata:
            _thread_manager.update_thread(
                thread_id,
                message_count=current_metadata.message_count + 1
            )
    
    try:
        # Run the graph
        response = await graph.chat(request.message, thread_id)
        
        # Sync thread metadata
        state = await graph.get_state(thread_id)
        if state and _thread_manager:
            _thread_manager.sync_from_state(thread_id, state)
        
        # Update debug info
        if state:
            _last_debug_info["last_tool_calls"] = state.get("current_turn_tools", [])
        
        # Get updated session
        session = await get_session()
        
        return {
            "response": response,
            "session": session,
            "thread_id": thread_id,
        }
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- WebSocket for streaming ---

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat."""
    global _current_thread_id, _last_debug_info
    
    await websocket.accept()
    logger.info("WebSocket connected")

    # Extract user_id from request state (set by APIKeyMiddleware)
    ws_user_id = getattr(websocket.state, "user_id", _profile.user_id if _profile else "varun")

    # Register for push notifications and deliver any pending ones
    if _notification_queue:
        await _notification_queue.register_ws(ws_user_id, websocket)
        try:
            unread = await _notification_queue.get_unread(ws_user_id)
            if unread:
                for n in unread:
                    await websocket.send_json({"type": "notification", **n})
                await _notification_queue.mark_read([n["id"] for n in unread])
                logger.info(f"Delivered {len(unread)} pending notifications to {ws_user_id}")
        except Exception as e:
            logger.warning(f"Failed to deliver pending notifications: {e}")

    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "chat":
                message = data.get("message", "")
                model = data.get("model")
                thread_id = data.get("thread_id") or _current_thread_id
                
                # Parse model info
                if model and "/" in model:
                    provider, model_name = model.split("/", 1)
                else:
                    provider = _llm_config.provider.value if _llm_config else "mock"
                    model_name = _llm_config.model if _llm_config else "mock-default"
                
                logger.info(f"Chat request: model={model}, parsed provider={provider}, model_name={model_name}")
                
                # Get graph with the specified model
                graph = await get_or_create_graph(provider, model_name)
                
                # Ensure thread exists - create with current model
                if not thread_id:
                    thread_id = _thread_manager.create_thread(
                        "New Conversation",
                        model_provider=provider,
                        model_name=model_name
                    )
                    _current_thread_id = thread_id
                else:
                    # Thread exists - update its model if this is the first message
                    metadata = _thread_manager.get_thread(thread_id)
                    if metadata and metadata.message_count == 0:
                        # First message - lock in the model being used
                        if metadata.model_provider != provider or metadata.model_name != model_name:
                            _thread_manager.update_thread(
                                thread_id,
                                model_provider=provider,
                                model_name=model_name
                            )
                            logger.info(f"Updated thread {thread_id} model to {provider}/{model_name} on first message")
                
                # Increment message count immediately when user sends a message
                # This ensures the thread persists in history even if LLM fails
                current_metadata = _thread_manager.get_thread(thread_id)
                if current_metadata:
                    _thread_manager.update_thread(
                        thread_id,
                        message_count=current_metadata.message_count + 1
                    )
                
                # Send thinking indicator
                await websocket.send_json({"type": "thinking", "status": True})
                
                try:
                    # Set up real-time log callback for this thread
                    from llm_logger import get_llm_logger
                    llm_logger = get_llm_logger()
                    
                    # Get the current event loop for scheduling async tasks from sync callback
                    import asyncio
                    loop = asyncio.get_running_loop()
                    
                    def log_callback(entry: dict):
                        """Send log entry to frontend in real-time."""
                        loop.create_task(websocket.send_json({
                            "type": "log_entry",
                            "entry": entry
                        }))
                    
                    llm_logger.set_log_callback(thread_id, log_callback)
                    
                    # Create streaming callback for real-time token streaming
                    streamed_content = []  # Track what we've streamed
                    
                    async def stream_callback(token: str):
                        """Send streaming token to frontend."""
                        streamed_content.append(token)
                        await websocket.send_json({
                            "type": "stream_token",
                            "token": token
                        })
                    
                    # Stream graph execution for real-time updates
                    from langchain_core.messages import AIMessage, HumanMessage
                    final_response = None
                    
                    async for event in graph.stream_chat(message, thread_id, stream_callback=stream_callback):
                        # event is a dict with node name as key and output as value
                        for node_name, node_output in event.items():
                            # Check for AIMessages with tool calls (thinking messages)
                            if node_name == "call_llm" and node_output:
                                messages = node_output.get("messages", [])
                                for msg in messages:
                                    if isinstance(msg, AIMessage) and msg.tool_calls:
                                        # This was a tool-calling response, not a final response
                                        # Send stream_cancel to clear any streamed content
                                        # and replace it with a thinking message
                                        if streamed_content:
                                            await websocket.send_json({"type": "stream_cancel"})
                                            streamed_content.clear()
                                        
                                        # Determine message type: "thinking" if has content, "tool_execution" if just tools
                                        has_content = msg.content and msg.content.strip()
                                        msg_type = "thinking" if has_content else "tool_execution"
                                        
                                        # Send thinking/tool_execution message to frontend
                                        tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
                                        await websocket.send_json({
                                            "type": "thinking_message",
                                            "msg_type": msg_type,
                                            "content": msg.content or "",
                                            "tool_calls": tool_names,
                                        })
                            
                            # Capture final response (store_turn means we're done)
                            if node_name == "store_turn":
                                # Get the final state to extract response
                                pass
                    
                    # Signal end of streaming (if we streamed anything)
                    if streamed_content:
                        await websocket.send_json({"type": "stream_end"})
                    
                    # Get final state and extract response
                    state = await graph.get_state(thread_id)
                    
                    # Find the final response - only look at messages AFTER the last HumanMessage
                    # This prevents showing a previous turn's response when current turn returns empty
                    if state:
                        messages = state.get("messages", [])
                        
                        # Find the index of the last user message (current turn start)
                        last_user_idx = -1
                        for i, msg in enumerate(messages):
                            if isinstance(msg, HumanMessage):
                                last_user_idx = i
                        
                        # Only look at messages after the last user message
                        current_turn_messages = messages[last_user_idx + 1:] if last_user_idx >= 0 else messages
                        
                        for msg in reversed(current_turn_messages):
                            if isinstance(msg, AIMessage):
                                has_tool_calls = msg.tool_calls and len(msg.tool_calls) > 0
                                if not has_tool_calls and msg.content and msg.content.strip():
                                    final_response = msg.content
                                    break
                        
                        # NO FALLBACK to previous turn's messages - that's the bug!
                        # If there's no response in current turn, say so explicitly
                    
                    if not final_response:
                        final_response = "I processed your request but the model returned an empty response. This may happen when the model exhausts its reasoning budget on tool calls."
                    
                    logger.info(f"State after chat: turn_count={state.get('turn_count', 0) if state else 'N/A'}, "
                               f"tool_calls={len(state.get('current_turn_tools', [])) if state else 0}, "
                               f"distilled={bool(state.get('distilled_summary')) if state else False}")
                    if state and _thread_manager:
                        _thread_manager.sync_from_state(thread_id, state)
                    
                    # Get thread metadata
                    metadata = _thread_manager.get_thread(thread_id)
                    
                    # Build thread_state from state (always show meaningful info)
                    state_parts = []
                    if state:
                        turn_count = state.get("turn_count", 0)
                        state_parts.append(f"🔄 Turns: {turn_count}")
                        
                        mode = state.get("mode", "idle")
                        mode_display = {"idle": "💤 Idle", "logging": "📝 Logging", "querying": "🔍 Querying"}.get(mode, f"⚡ {mode}")
                        state_parts.append(mode_display)
                        
                        target_date = state.get("target_date")
                        if target_date:
                            state_parts.append(f"📅 Date: {target_date}")
                        
                        # Message count
                        messages = state.get("messages", [])
                        user_msgs = sum(1 for m in messages if hasattr(m, 'type') and m.type == 'human')
                        ai_msgs = sum(1 for m in messages if hasattr(m, 'type') and m.type == 'ai')
                        state_parts.append(f"💬 Messages: {user_msgs} user, {ai_msgs} assistant")
                        
                        pending_entities = len(state.get("pending_entities", []))
                        pending_events = len(state.get("pending_events", []))
                        if pending_entities > 0 or pending_events > 0:
                            state_parts.append(f"📋 Pending: {pending_events} events, {pending_entities} entities")
                        
                        if state.get("skeleton"):
                            skeleton_data = state.get("skeleton", {})
                            gaps = len(skeleton_data.get("gaps", []))
                            events = len(skeleton_data.get("events", []))
                            state_parts.append(f"🗓️ Skeleton: {events} events, {gaps} gaps")
                    
                    # Build context summary (what's being passed to LLM)
                    context_parts = []
                    if state:
                        # Distilled summary takes priority
                        distilled = state.get("distilled_summary", "")
                        if distilled:
                            context_parts.append(f"📝 Distilled History:\n{distilled}")
                        else:
                            # Show recent message context
                            messages = state.get("messages", [])
                            if messages:
                                recent_count = min(len(messages), 6)
                                context_parts.append(f"💬 Recent: Last {recent_count} messages in context")
                        
                        # Skills loaded
                        skills = state.get("skills_content", "")
                        if skills:
                            # Count skills by looking for headers
                            skill_count = skills.count("##")
                            context_parts.append(f"📚 Skills: {skill_count} domain sections loaded")
                        
                        # Skeleton context
                        if state.get("skeleton") and state.get("mode") == "logging":
                            context_parts.append("🗓️ Timeline skeleton included in context")
                        
                        # Owner ID cached
                        if state.get("owner_id"):
                            context_parts.append(f"👤 Owner ID cached")
                    
                    if not context_parts:
                        context_parts.append("Base system prompt only")
                    
                    context_summary = "\n".join(context_parts)
                    
                    # Send response
                    model_name = metadata.model_name if metadata else None
                    await websocket.send_json({
                        "type": "response",
                        "content": final_response,
                        "session": {
                            "mode": state.get("mode", "idle") if state else "idle",
                            "target_date": state.get("target_date") if state else None,
                            "turn_count": state.get("turn_count", 0) if state else 0,
                            "thread_state": "\n".join(state_parts) if state_parts else "",
                            "distilled_summary": context_summary,
                        },
                        "detected_date": state.get("target_date") if state else None,
                        "usage": _get_last_turn_usage(state, model_name),
                        "tool_calls": state.get("current_turn_tools", []) if state else [],
                        "thread_id": thread_id,
                        "thread_title": metadata.title if metadata else "New Conversation",
                    })
                    
                    # Send debug info
                    tool_calls = state.get("current_turn_tools", []) if state else []
                    skeleton_data = state.get("skeleton") if state else None
                    skeleton = skeleton_data.get("summary", "") if skeleton_data else ""
                    
                    await websocket.send_json({
                        "type": "debug",
                        "tool_calls": tool_calls,
                        "skeleton": skeleton,
                    })
                    
                except Exception as e:
                    logger.error(f"WebSocket chat error: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e)
                    })
                finally:
                    # Clear log callback
                    llm_logger.set_log_callback(thread_id, None)
                    await websocket.send_json({"type": "thinking", "status": False})
            
            elif data.get("type") == "get_tools":
                tools_data = await get_tools()
                await websocket.send_json({"type": "tools", **tools_data})
            
            elif data.get("type") == "get_debug":
                debug_data = await get_debug_info()
                await websocket.send_json({"type": "debug_full", **debug_data})
            
            elif data.get("type") == "get_threads":
                threads_data = await list_threads()
                await websocket.send_json({"type": "threads", **threads_data})
            
            elif data.get("type") == "new_thread":
                title = data.get("title", "New Conversation")
                result = await create_thread(NewThreadRequest(title=title))
                await websocket.send_json({"type": "thread_created", **result})
            
            elif data.get("type") == "load_thread":
                thread_id = data.get("thread_id")
                if thread_id:
                    try:
                        result = await load_thread(thread_id)
                        await websocket.send_json({"type": "thread_loaded", **result})
                    except HTTPException as e:
                        await websocket.send_json({"type": "error", "error": e.detail})
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if _notification_queue:
            await _notification_queue.unregister_ws(ws_user_id, websocket)


# --- Agent Infrastructure Endpoints ---


class ScheduleRequest(BaseModel):
    agent_name: str
    skill: str
    cron: str
    config: Optional[dict] = None


@app.get("/api/scheduler")
async def list_schedules(request: Request):
    """List active scheduled agents for the current user."""
    if not _scheduler:
        return {"schedules": []}
    user_id = getattr(request.state, "user_id", _profile.user_id if _profile else "varun")
    schedules = await _scheduler.list_schedules(user_id)
    return {"schedules": schedules}


@app.post("/api/scheduler")
async def create_schedule(request: Request, body: ScheduleRequest):
    """Register a new scheduled agent."""
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    user_id = getattr(request.state, "user_id", _profile.user_id if _profile else "varun")
    sched_id = await _scheduler.schedule(
        user_id=user_id,
        agent_name=body.agent_name,
        skill=body.skill,
        cron_expr=body.cron,
        config=body.config,
    )
    return {"schedule_id": sched_id, "agent_name": body.agent_name, "cron": body.cron}


@app.delete("/api/scheduler/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Deactivate a scheduled agent."""
    if not _scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    success = await _scheduler.unschedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deactivated", "schedule_id": schedule_id}


@app.get("/api/notifications")
async def get_notifications(request: Request, limit: int = 20):
    """Get unread notifications for the current user."""
    if not _notification_queue:
        return {"notifications": []}
    user_id = getattr(request.state, "user_id", _profile.user_id if _profile else "varun")
    notifications = await _notification_queue.get_unread(user_id, limit=limit)
    return {"notifications": notifications, "count": len(notifications)}


@app.post("/api/notifications/read")
async def mark_notifications_read(request: Request, body: dict):
    """Mark notifications as read."""
    if not _notification_queue:
        return {"marked": 0}
    ids = body.get("ids", [])
    count = await _notification_queue.mark_read(ids)
    return {"marked": count}


@app.get("/api/artifacts")
async def list_artifacts(request: Request, type: Optional[str] = None, limit: int = 20):
    """List recent agent artifacts for the current user."""
    if not _notification_queue:
        return {"artifacts": []}
    user_id = getattr(request.state, "user_id", _profile.user_id if _profile else "varun")
    artifacts = await _notification_queue.list_artifacts(user_id, artifact_type=type, limit=limit)
    return {"artifacts": artifacts}


@app.get("/api/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    """Get a specific artifact by ID."""
    if not _notification_queue:
        raise HTTPException(status_code=503, detail="Artifact store not initialized")
    artifact = await _notification_queue.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


# --- Static files ---

static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def root():
    """Serve the main page."""
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Journal Agent API (LangGraph)", "docs": "/docs"}


# --- Run server ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
