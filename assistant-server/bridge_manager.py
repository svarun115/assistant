"""
BridgeManager — per-user MCPToolBridge lifecycle management.

Each user gets their own MCPToolBridge instance with user-specific credentials
injected as HTTP headers on MCP server connections. Bridges are cached per
user_id and reused across sessions for the same user.

Usage:
    manager = BridgeManager(base_servers, credential_store)
    bridge = await manager.get_bridge("varun")   # creates or returns cached
    await manager.invalidate("varun")             # force reconnect (e.g. after token refresh)
    await manager.cleanup()                       # shutdown all bridges
"""

import copy
import logging
from dataclasses import replace
from typing import Optional

from config import MCPServerConfig
from credential_store import CredentialStore
from mcp_bridge import MCPToolBridge

logger = logging.getLogger(__name__)

# Maps MCP server name → (user_credentials.service, header_name)
# Servers not listed here use operator credentials from env (no per-user override).
SERVER_CREDENTIAL_MAP: dict[str, tuple[str, str]] = {
    "garmin": ("garmin", "X-Garmin-Token"),
    "google-workspace": ("google", "Authorization"),
    "splitwise": ("splitwise", "X-Splitwise-Key"),
}

# How to format token_data into header value per service
def _format_header_value(service: str, token_data: dict) -> Optional[str]:
    """
    Convert decrypted token_data dict into the header value string for a service.

    Returns None if the token_data doesn't have the required fields.
    """
    if service == "google":
        access_token = token_data.get("access_token")
        return f"Bearer {access_token}" if access_token else None
    elif service == "garmin":
        # Garth tokens are a nested JSON — pass as-is
        import json
        return json.dumps(token_data)
    elif service == "splitwise":
        return token_data.get("api_key")
    else:
        # Generic: if there's an "api_key" or "token" field, use it
        return token_data.get("api_key") or token_data.get("token")


class BridgeManager:
    """
    Manages per-user MCPToolBridge instances.

    Each user gets their own bridge with user-specific credentials injected
    as HTTP headers. Bridges are cached per user_id.

    For the single-user case (no CredentialStore), creates one shared bridge
    using the base server configs as-is (operator credentials from env).
    """

    def __init__(
        self,
        base_servers: list[MCPServerConfig],
        credential_store: Optional[CredentialStore] = None,
    ):
        self._base_servers = base_servers
        self._credential_store = credential_store
        self._bridges: dict[str, MCPToolBridge] = {}  # user_id → bridge

    async def get_bridge(self, user_id: str) -> MCPToolBridge:
        """
        Get or create an MCPToolBridge for this user.

        If CredentialStore is available, injects user-specific auth headers.
        Otherwise, uses base server configs as-is (operator credentials).
        """
        if user_id in self._bridges and self._bridges[user_id].is_connected():
            return self._bridges[user_id]

        # Build server list with per-user headers
        servers = await self._build_user_servers(user_id)

        bridge = MCPToolBridge()
        await bridge.__aenter__()
        await bridge.connect(servers)

        self._bridges[user_id] = bridge
        logger.info(f"Created MCPToolBridge for user '{user_id}' ({len(bridge.tool_names)} tools)")
        return bridge

    async def _build_user_servers(self, user_id: str) -> list[MCPServerConfig]:
        """
        Clone base_servers with user-specific auth headers from CredentialStore.

        Servers not in SERVER_CREDENTIAL_MAP are passed through unchanged
        (they use operator credentials from env).
        """
        if not self._credential_store:
            return self._base_servers

        servers = []
        for base in self._base_servers:
            mapping = SERVER_CREDENTIAL_MAP.get(base.name)
            if not mapping:
                # No per-user credentials for this server
                servers.append(base)
                continue

            service_name, header_name = mapping
            token_data = await self._credential_store.get(user_id, service_name)
            if not token_data:
                # No credentials stored — use base config (operator creds)
                servers.append(base)
                continue

            header_value = _format_header_value(service_name, token_data)
            if not header_value:
                logger.warning(
                    f"Could not format header for {base.name}/{service_name} "
                    f"(user={user_id}) — using operator credentials"
                )
                servers.append(base)
                continue

            # Clone the config with injected header
            new_headers = dict(base.headers) if base.headers else {}
            new_headers[header_name] = header_value
            server_copy = replace(base, headers=new_headers)
            servers.append(server_copy)
            logger.debug(f"Injected {header_name} for {base.name} (user={user_id})")

        return servers

    async def invalidate(self, user_id: str) -> None:
        """
        Force-close a user's bridge (e.g. after credential refresh).
        Next call to get_bridge() will create a fresh one.
        """
        bridge = self._bridges.pop(user_id, None)
        if bridge:
            try:
                await bridge.__aexit__(None, None, None)
                logger.info(f"Invalidated bridge for user '{user_id}'")
            except Exception as e:
                logger.warning(f"Error closing bridge for '{user_id}': {e}")

    async def cleanup(self) -> None:
        """Shut down all bridges."""
        for user_id in list(self._bridges.keys()):
            await self.invalidate(user_id)
        logger.info("BridgeManager: all bridges cleaned up")
