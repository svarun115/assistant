"""
AgentScheduler — background asyncio task that polls assistant_system.scheduler
and fires due background agents.

Architecture:
  - Runs as a long-lived asyncio.Task alongside the FastAPI server
  - Polls scheduler table every POLL_INTERVAL seconds
  - For each due row: updates next_run, then calls on_due_agent callback
  - on_due_agent is provided by AgentSpawner (injected after 2d is built)
  - Until AgentSpawner exists, callback is a no-op — scheduler still tracks
    and advances schedules, just doesn't run anything

Usage:
    # In web_server.py startup:
    scheduler = AgentScheduler(auth_pool, on_due_agent=spawner.spawn_background)
    await scheduler.start()

    # In web_server.py shutdown:
    await scheduler.stop()

    # Register a new cron job (e.g. daily email triage at 7am):
    await scheduler.schedule(
        user_id="varun",
        agent_name="email-triage",
        skill="email-triage",
        cron_expr="0 7 * * *",
        config={"max_emails": 20},
    )
"""

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# How often to check for due agents (seconds)
POLL_INTERVAL = 60


def _next_run(cron_expr: str, after: Optional[datetime] = None) -> datetime:
    """Compute the next run time for a cron expression using croniter."""
    from croniter import croniter
    base = after or datetime.now(timezone.utc)
    # croniter works with naive datetimes; strip tz then re-attach
    base_naive = base.replace(tzinfo=None)
    return croniter(cron_expr, base_naive).get_next(datetime)


class AgentScheduler:
    """
    Polls assistant_system.scheduler table and fires due agents.

    Designed to be loosely coupled from AgentSpawner: it calls on_due_agent
    (an async callback) rather than importing spawner directly. This lets
    scheduler.py be built and tested before agent_spawner.py exists.
    """

    def __init__(
        self,
        pg_pool,
        on_due_agent: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
        poll_interval: int = POLL_INTERVAL,
    ):
        """
        Args:
            pg_pool: psycopg AsyncConnectionPool connected to assistant_system.
            on_due_agent: async callable(user_id, agent_name, skill, config) invoked
                          when a scheduled agent is due. If None, schedules are
                          advanced (next_run updated) but no agent is fired.
            poll_interval: Seconds between scheduler polls (default 60).
        """
        self._pool = pg_pool
        self._on_due_agent = on_due_agent
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the scheduler background loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="agent-scheduler")
        logger.info(f"AgentScheduler started (poll_interval={self._poll_interval}s)")

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AgentScheduler stopped")

    def set_callback(self, on_due_agent: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """Hot-swap the agent callback. Used to inject AgentSpawner after construction."""
        self._on_due_agent = on_due_agent

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}", exc_info=True)
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def _tick(self) -> None:
        """Find all due schedules and fire them concurrently."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, user_id, agent_name, skill, cron, config "
                "FROM scheduler "
                "WHERE is_active = TRUE AND next_run <= NOW()"
            )
            due = await cur.fetchall()

        if not due:
            return

        logger.info(f"Scheduler: {len(due)} agent(s) due")
        for row in due:
            asyncio.create_task(self._fire(row), name=f"scheduled-{row[2]}")

    async def _fire(self, row: tuple) -> None:
        """Fire a single scheduled agent and advance its next_run."""
        sched_id, user_id, agent_name, skill, cron_expr, config = row

        # Advance schedule before firing so re-check can't double-fire
        next_run_dt = _next_run(cron_expr)
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    "UPDATE scheduler SET last_run = NOW(), next_run = %s WHERE id = %s",
                    (next_run_dt, sched_id),
                )
        except Exception as e:
            logger.error(f"Failed to advance schedule {sched_id}: {e}")
            return

        logger.info(
            f"Firing: agent={agent_name} user={user_id} skill={skill} "
            f"next_run={next_run_dt.isoformat()}"
        )

        if self._on_due_agent:
            try:
                await self._on_due_agent(
                    user_id=user_id,
                    agent_name=agent_name,
                    skill=skill,
                    config=config or {},
                )
            except Exception as e:
                logger.error(f"Scheduled agent '{agent_name}' failed for user '{user_id}': {e}", exc_info=True)
        else:
            logger.debug(f"No on_due_agent callback — schedule advanced, nothing fired")

    # ------------------------------------------------------------------
    # Admin helpers (called by API endpoints / admin console)
    # ------------------------------------------------------------------

    async def schedule(
        self,
        user_id: str,
        agent_name: str,
        skill: str,
        cron_expr: str,
        config: Optional[dict] = None,
    ) -> str:
        """Register a new scheduled agent. Returns the schedule UUID."""
        next_run_dt = _next_run(cron_expr)
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO scheduler (user_id, agent_name, skill, cron, next_run, config) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, agent_name, skill, cron_expr, next_run_dt, json.dumps(config or {})),
            )
            row = await cur.fetchone()
            sched_id = str(row[0])
        logger.info(f"Scheduled: {agent_name} for {user_id} ({cron_expr}), first run {next_run_dt}")
        return sched_id

    async def unschedule(self, schedule_id: str) -> bool:
        """Deactivate a schedule. Returns True if it was found and deactivated."""
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "UPDATE scheduler SET is_active = FALSE WHERE id = %s AND is_active = TRUE",
                (schedule_id,),
            )
            return result.rowcount > 0

    async def sync_from_heartbeats(self, agent_loader, user_id: str) -> dict[str, int]:
        """
        Sync schedule declarations from all installed agent instances' HEARTBEAT.md
        into the scheduler table.

        Replaces seed_schedules.py for agent-owned schedules. Called at startup
        after AgentSeeder.sync() and whenever a new agent instance is created.

        Returns dict with 'created', 'updated', 'unchanged' counts.
        """
        schedules = await agent_loader.get_all_schedules(user_id)
        counts = {"created": 0, "updated": 0, "unchanged": 0}

        for sched in schedules:
            agent_name = sched.get("agent_name")
            skill = sched.get("skill", agent_name)
            cron_expr = sched.get("cron")
            task = sched.get("task", "")
            artifact_type = sched.get("artifact_type", "")
            description = sched.get("description", "")

            if not agent_name or not cron_expr:
                logger.warning(f"Heartbeat schedule missing agent_name or cron: {sched}")
                continue

            config = {"task": task, "artifact_type": artifact_type}
            if description:
                config["description"] = description

            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT id, cron, config FROM scheduler "
                    "WHERE user_id=%s AND agent_name=%s AND is_active=TRUE",
                    (user_id, agent_name),
                )
                existing = await cur.fetchone()

                if existing is None:
                    # New schedule from heartbeat
                    next_run_dt = _next_run(cron_expr)
                    await conn.execute(
                        "INSERT INTO scheduler (user_id, agent_name, skill, cron, next_run, config) "
                        "VALUES (%s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (user_id, agent_name) WHERE is_active=TRUE DO NOTHING",
                        (user_id, agent_name, skill, cron_expr, next_run_dt, json.dumps(config)),
                    )
                    counts["created"] += 1
                    logger.info(f"Heartbeat schedule registered: {agent_name} ({cron_expr}) for {user_id}")
                else:
                    existing_id, existing_cron, existing_config = existing
                    if existing_cron == cron_expr:
                        counts["unchanged"] += 1
                    else:
                        # Cron changed in heartbeat — update (preserve next_run logic)
                        next_run_dt = _next_run(cron_expr)
                        await conn.execute(
                            "UPDATE scheduler SET cron=%s, next_run=%s, config=%s "
                            "WHERE id=%s",
                            (cron_expr, next_run_dt, json.dumps(config), existing_id),
                        )
                        counts["updated"] += 1
                        logger.info(f"Heartbeat schedule updated: {agent_name} cron {existing_cron} → {cron_expr}")

        if any(v > 0 for v in counts.values()):
            logger.info(f"sync_from_heartbeats for {user_id}: {counts}")
        return counts

    async def list_schedules(self, user_id: str) -> list[dict]:
        """List active schedules for a user, ordered by next run time."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, agent_name, skill, cron, next_run, last_run, config "
                "FROM scheduler WHERE user_id = %s AND is_active = TRUE "
                "ORDER BY next_run",
                (user_id,),
            )
            rows = await cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "agent_name": r[1],
                "skill": r[2],
                "cron": r[3],
                "next_run": r[4].isoformat() if r[4] else None,
                "last_run": r[5].isoformat() if r[5] else None,
                "config": r[6] or {},
            }
            for r in rows
        ]
