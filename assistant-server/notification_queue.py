"""
NotificationQueue + ArtifactStore — agent output delivery pipeline.

Two responsibilities kept in one module because they're always used together:
  1. ArtifactStore: persist agent output (daily_plan, email_digest, etc.)
     to assistant_system.artifacts.
  2. NotificationQueue: deliver agent completion messages to the user.
     - If the user has an open WebSocket → push immediately.
     - Otherwise → store in assistant_system.notifications for next session.

Usage from AgentSpawner (or any background agent):

    # Write the agent's output:
    artifact_id = await nq.write_artifact(
        user_id="varun",
        agent_id="email-triage",
        artifact_type="email_digest",
        content=markdown_summary,
    )

    # Notify the user:
    await nq.post(
        user_id="varun",
        from_agent="email-triage",
        message="Your email digest is ready (12 emails processed).",
        priority="normal",
        artifact_id=artifact_id,
    )

Usage from WebSocket handler (web_server.py):

    # Register when WS opens:
    nq.register_ws(user_id, websocket)

    # Unregister when WS closes:
    nq.unregister_ws(user_id, websocket)

    # On session start — push pending notifications to the new client:
    unread = await nq.get_unread(user_id)
    for n in unread:
        await websocket.send_json({"type": "notification", **n})
    if unread:
        await nq.mark_read([n["id"] for n in unread])
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class NotificationQueue:
    """
    Notification delivery and artifact storage for background agents.

    Thread-safe: uses asyncio.Lock for the WebSocket registry.
    """

    def __init__(self, pg_pool):
        """
        Args:
            pg_pool: psycopg AsyncConnectionPool connected to assistant_system.
        """
        self._pool = pg_pool
        # user_id → list of active WebSocket objects
        self._active_ws: dict[str, list] = defaultdict(list)
        self._ws_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # WebSocket registry
    # ------------------------------------------------------------------

    async def register_ws(self, user_id: str, ws: Any) -> None:
        """Register an open WebSocket connection for a user."""
        async with self._ws_lock:
            if ws not in self._active_ws[user_id]:
                self._active_ws[user_id].append(ws)
                logger.debug(f"NotificationQueue: registered WS for {user_id}")

    async def unregister_ws(self, user_id: str, ws: Any) -> None:
        """Unregister a WebSocket (call when it closes)."""
        async with self._ws_lock:
            try:
                self._active_ws[user_id].remove(ws)
                logger.debug(f"NotificationQueue: unregistered WS for {user_id}")
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Artifact store
    # ------------------------------------------------------------------

    async def write_artifact(
        self,
        user_id: str,
        agent_id: str,
        artifact_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Persist agent output to assistant_system.artifacts.

        Args:
            user_id: Owner of the artifact.
            agent_id: The agent that produced it (e.g. "email-triage").
            artifact_type: Type tag (e.g. "email_digest", "daily_plan", "retro").
            content: Artifact body (markdown, JSON string, etc.).
            metadata: Optional JSON-serializable metadata dict.

        Returns:
            Artifact UUID string.
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO artifacts (user_id, agent_id, type, content, metadata) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (user_id, agent_id, artifact_type, content, json.dumps(metadata or {})),
            )
            row = await cur.fetchone()
            artifact_id = str(row[0])
        logger.info(f"Artifact written: type={artifact_type} agent={agent_id} user={user_id} id={artifact_id}")
        return artifact_id

    async def get_artifact(self, artifact_id: str) -> Optional[dict]:
        """Retrieve a single artifact by ID."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, user_id, agent_id, type, content, metadata, created_at "
                "FROM artifacts WHERE id = %s AND is_deleted = FALSE",
                (artifact_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "user_id": row[1],
            "agent_id": row[2],
            "type": row[3],
            "content": row[4],
            "metadata": row[5] or {},
            "created_at": row[6].isoformat(),
        }

    async def list_artifacts(
        self,
        user_id: str,
        artifact_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """List recent artifacts for a user, optionally filtered by type."""
        query = (
            "SELECT id, agent_id, type, content, metadata, created_at FROM artifacts "
            "WHERE user_id = %s AND is_deleted = FALSE"
        )
        params: list = [user_id]
        if artifact_type:
            query += " AND type = %s"
            params.append(artifact_type)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        async with self._pool.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "agent_id": r[1],
                "type": r[2],
                # Truncate content preview to 200 chars for listing
                "content_preview": r[3][:200] + "..." if len(r[3]) > 200 else r[3],
                "metadata": r[4] or {},
                "created_at": r[5].isoformat(),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Notification delivery
    # ------------------------------------------------------------------

    async def post(
        self,
        user_id: str,
        from_agent: str,
        message: str,
        priority: str = "normal",
        to_thread_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> str:
        """
        Write a notification to the DB and push to active WebSocket(s) if available.

        Args:
            user_id: The recipient user.
            from_agent: Name of the agent that produced this notification.
            message: Human-readable notification message for COS/user.
            priority: "urgent", "normal", or "low".
            to_thread_id: Specific COS thread to deliver to (None = any active).
            artifact_id: UUID of an associated artifact, if any.

        Returns:
            Notification UUID string.
        """
        # Write to DB first
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO notifications "
                "(user_id, from_agent, to_thread_id, message, priority, artifact_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    user_id,
                    from_agent,
                    to_thread_id,
                    message,
                    priority,
                    artifact_id,
                ),
            )
            row = await cur.fetchone()
            notif_id = str(row[0])

        logger.info(
            f"Notification: from={from_agent} user={user_id} "
            f"priority={priority} id={notif_id}"
        )

        # Push to active WebSocket(s) if any are open
        payload = {
            "type": "notification",
            "id": notif_id,
            "from_agent": from_agent,
            "message": message,
            "priority": priority,
            "artifact_id": artifact_id,
        }
        async with self._ws_lock:
            ws_list = list(self._active_ws.get(user_id, []))

        for ws in ws_list:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug(f"Failed to push notification to WS for {user_id}: {e}")

        return notif_id

    async def get_unread(self, user_id: str, limit: int = 20) -> list[dict]:
        """
        Get unread notifications for a user, newest first.

        Called at session start so COS can surface pending notifications.
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, from_agent, message, priority, artifact_id, created_at "
                "FROM notifications "
                "WHERE user_id = %s AND read_at IS NULL "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
            rows = await cur.fetchall()
        return [
            {
                "id": str(r[0]),
                "from_agent": r[1],
                "message": r[2],
                "priority": r[3],
                "artifact_id": str(r[4]) if r[4] else None,
                "created_at": r[5].isoformat(),
            }
            for r in rows
        ]

    async def mark_read(self, notification_ids: list[str]) -> int:
        """
        Mark notifications as read. Returns count of rows updated.

        Call after pushing unread notifications to a newly-opened session.
        """
        if not notification_ids:
            return 0
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "UPDATE notifications SET read_at = NOW() "
                "WHERE id = ANY(%s::uuid[]) AND read_at IS NULL",
                (notification_ids,),
            )
            return result.rowcount
