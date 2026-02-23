"""
AgentSpawner — creates and runs the three agent types in the COS architecture.

Agent types:
  1. Task agent      — ephemeral, inline sub-task. COS awaits the result directly.
                       Restricted tool set (only the skill's allowed servers).
                       Returns text; no notification.

  2. Background agent — fire-and-forget asyncio task.
                        Writes result as artifact, posts notification when done.
                        Used for scheduled work (email triage, daily plan, etc.)

  3. Foreground agent — creates a persistent LangGraph thread.
                        User can switch to it like a normal conversation.
                        COS optionally runs a pre-task to warm state.

Usage from COS skill (via tool call or direct invocation):

    # Task agent (inline, await result):
    result = await spawner.invoke_task(
        user_id="varun",
        skill="expenses",
        task="Summarize Splitwise balances for March",
        context={"month": "2026-03"},
    )

    # Background agent (fire-and-forget):
    agent_id = await spawner.spawn_background(
        user_id="varun",
        agent_name="email-triage",
        skill="email-triage",
        config={"max_emails": 30},
    )

    # Foreground agent (user switches to new thread):
    thread_id = await spawner.spawn_foreground(
        user_id="varun",
        skill="financial-advisor",
        pre_task="Load portfolio summary and prepare for user questions",
    )
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class AgentSpawner:
    """
    Creates and runs the three agent types in the COS architecture.

    Loosely coupled: receives factories and managers rather than importing
    web_server globals. This makes testing and future multi-process
    deployment straightforward.
    """

    def __init__(
        self,
        graph_factory: Callable[..., Coroutine[Any, Any, Any]],
        bridge_manager,
        thread_manager,
        notification_queue,
        agent_loader=None,
        default_user_id: str = "varun",
    ):
        """
        Args:
            graph_factory: Async callable that returns a JournalGraph.
                           Signature: async (provider=None, model=None, mcp_bridge=None,
                                             user_id=None, allow_operator_llm=True) -> JournalGraph
                           This is get_or_create_graph from web_server.py.
            bridge_manager: BridgeManager — provides per-user MCPToolBridge.
            thread_manager: ThreadManager — creates and tracks threads.
            notification_queue: NotificationQueue — delivers results.
            agent_loader: AgentLoader — resolves agent definitions from DB.
                          Used to get system_prompt, allowed_servers, bootstrap_md
                          for foreground and task agents.
            default_user_id: Fallback user_id (single-user mode).
        """
        self._graph_factory = graph_factory
        self._bridge_manager = bridge_manager
        self._thread_manager = thread_manager
        self._nq = notification_queue
        self._agent_loader = agent_loader
        self._default_user = default_user_id

    # ------------------------------------------------------------------
    # 1. Task agent — ephemeral, inline, COS awaits result
    # ------------------------------------------------------------------

    async def invoke_task(
        self,
        user_id: str,
        skill: str,
        task: str,
        context: Optional[dict] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Run a task agent and return its text response.

        Creates a fresh (in-memory) LangGraph thread so task state never
        pollutes the COS conversation. Uses the user's bridge + BYOK key.

        Args:
            user_id: The user this task runs on behalf of.
            skill: The skill to load (sets allowed MCP servers and system prompt).
            task: The task instruction string.
            context: Optional dict of additional context (merged into task message).
            provider / model: LLM override. Falls back to user's configured default.

        Returns:
            The agent's text response.
        """
        bridge = await self._bridge_manager.get_bridge(user_id)
        graph = await self._graph_factory(
            provider=provider,
            model=model,
            mcp_bridge=bridge,
            user_id=user_id,
            allow_operator_llm=True,
        )

        # Use a fresh ephemeral thread (UUID not tracked in ThreadManager)
        import uuid
        ephemeral_thread_id = f"task-{uuid.uuid4().hex[:12]}"

        # Build task message with optional context
        message = task
        if context:
            import json
            context_str = json.dumps(context, indent=2)
            message = f"{task}\n\nContext:\n{context_str}"

        # Inject skill activation prefix so the skill router picks the right skill
        if not message.startswith("/"):
            message = f"/{skill} {message}"

        logger.info(f"Task agent: skill={skill} user={user_id} thread={ephemeral_thread_id}")
        result = await graph.chat(message, ephemeral_thread_id, mcp_bridge=bridge)
        logger.info(f"Task agent complete: thread={ephemeral_thread_id} result_len={len(result)}")
        return result

    # ------------------------------------------------------------------
    # 2. Background agent — fire-and-forget, writes artifact + notification
    # ------------------------------------------------------------------

    async def spawn_background(
        self,
        user_id: str,
        agent_name: str,
        skill: str,
        config: Optional[dict] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Spawn a background agent as a fire-and-forget asyncio task.

        The agent runs, writes its output as an artifact, and posts a
        notification so COS can surface it on the user's next turn.

        Args:
            user_id: User this agent runs for.
            agent_name: Human-readable name (e.g. "email-triage").
            skill: The skill file to load.
            config: Agent-specific config (e.g. {"max_emails": 30}).
            provider / model: LLM override.

        Returns:
            A short agent_run_id string (for logging / tracking).
        """
        import uuid
        run_id = f"bg-{uuid.uuid4().hex[:12]}"
        asyncio.create_task(
            self._run_background(run_id, user_id, agent_name, skill, config or {}, provider, model),
            name=f"bg-agent-{agent_name}-{run_id}",
        )
        logger.info(f"Background agent spawned: {agent_name} run_id={run_id} user={user_id}")
        return run_id

    async def _run_background(
        self,
        run_id: str,
        user_id: str,
        agent_name: str,
        skill: str,
        config: dict,
        provider: Optional[str],
        model: Optional[str],
    ) -> None:
        """Execute a background agent, write artifact, post notification."""
        logger.info(f"Background agent starting: {agent_name} run_id={run_id}")
        artifact_id: Optional[str] = None

        try:
            bridge = await self._bridge_manager.get_bridge(user_id)
            graph = await self._graph_factory(
                provider=provider,
                model=model,
                mcp_bridge=bridge,
                user_id=user_id,
                allow_operator_llm=True,
            )

            import uuid
            bg_thread_id = f"bg-{uuid.uuid4().hex[:12]}"

            # Build task message from config
            import json
            task = config.get("task", f"Run {agent_name} skill and produce a summary.")
            if config:
                task += f"\n\nConfig:\n{json.dumps({k: v for k, v in config.items() if k != 'task'}, indent=2)}"

            message = f"/{skill} {task}" if not task.startswith("/") else task

            result = await graph.chat(message, bg_thread_id, mcp_bridge=bridge)

            # Write artifact
            artifact_id = await self._nq.write_artifact(
                user_id=user_id,
                agent_id=agent_name,
                artifact_type=skill,
                content=result,
                metadata={"run_id": run_id, "config": config},
            )

            # Post success notification
            content_preview = result[:120] + "..." if len(result) > 120 else result
            await self._nq.post(
                user_id=user_id,
                from_agent=agent_name,
                message=f"{agent_name} completed. {content_preview}",
                priority="normal",
                artifact_id=artifact_id,
            )
            logger.info(f"Background agent complete: {agent_name} run_id={run_id} artifact={artifact_id}")

        except Exception as e:
            logger.error(f"Background agent failed: {agent_name} run_id={run_id}: {e}", exc_info=True)
            # Post failure notification so COS knows something went wrong
            try:
                await self._nq.post(
                    user_id=user_id,
                    from_agent=agent_name,
                    message=f"{agent_name} failed: {e}",
                    priority="urgent",
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 3. Foreground agent — persistent thread, user switches to it
    # ------------------------------------------------------------------

    async def spawn_foreground(
        self,
        user_id: str,
        skill: str,
        title: Optional[str] = None,
        pre_task: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Create a persistent foreground agent thread.

        The user can switch to this thread in the UI to interact with the
        agent directly. COS can optionally pre-warm it with a context message.

        If AgentLoader is available, loads the agent's BOOTSTRAP.md as the
        pre_task if no pre_task is explicitly provided.

        Args:
            user_id: User this agent runs for.
            skill: The skill/domain for this agent (resolves via AgentLoader or skills.py).
            title: Thread title shown in the UI (defaults to skill name).
            pre_task: Optional warm-up message. If None, uses agent's BOOTSTRAP.md if available.
            provider / model: LLM override.

        Returns:
            thread_id of the new foreground agent thread.
        """
        # Resolve pre_task: explicit > agent's BOOTSTRAP.md > None
        effective_pre_task = pre_task
        if not effective_pre_task and self._agent_loader:
            try:
                definition = await self._agent_loader.resolve(skill, user_id)
                if definition.bootstrap_md:
                    effective_pre_task = definition.bootstrap_md
            except Exception:
                pass  # Agent not in DB yet — no bootstrap, use skill via SkillsLoader

        # Create a tracked thread in ThreadManager
        model_provider = provider or "claude"
        model_name = model or "claude-sonnet-4-6"
        thread_title = title or f"{skill.replace('-', ' ').title()} Agent"
        thread_id = self._thread_manager.create_thread(
            thread_title,
            model_provider=model_provider,
            model_name=model_name,
        )

        logger.info(f"Foreground agent created: skill={skill} thread={thread_id} user={user_id}")

        # Pre-warm if we have something to run
        if effective_pre_task:
            asyncio.create_task(
                self._prewarm_foreground(thread_id, user_id, skill, effective_pre_task, provider, model),
                name=f"prewarm-{skill}-{thread_id[:8]}",
            )

        return thread_id

    async def _prewarm_foreground(
        self,
        thread_id: str,
        user_id: str,
        skill: str,
        pre_task: str,
        provider: Optional[str],
        model: Optional[str],
    ) -> None:
        """Run the pre-warm message on the foreground agent's thread."""
        try:
            bridge = await self._bridge_manager.get_bridge(user_id)
            graph = await self._graph_factory(
                provider=provider,
                model=model,
                mcp_bridge=bridge,
                user_id=user_id,
                allow_operator_llm=True,
            )
            message = f"/{skill} {pre_task}" if not pre_task.startswith("/") else pre_task
            await graph.chat(message, thread_id, mcp_bridge=bridge)
            logger.info(f"Foreground pre-warm complete: thread={thread_id}")
        except Exception as e:
            logger.error(f"Foreground pre-warm failed: thread={thread_id}: {e}", exc_info=True)
