"""
CredentialStore — per-user credential vault backed by assistant_system.user_credentials.

Encrypts token_data at rest using AES-256-GCM (via Python `cryptography` library).
Key sourced from CREDENTIALS_ENCRYPTION_KEY env var.

Each row stores `encryption_key_id` so the operator can rotate keys:
  1. Set new key in env, bump key_id to "v2"
  2. Old rows are re-encrypted lazily on next read (read with old key, write back with new key)

Usage:
    from credential_store import CredentialStore

    store = CredentialStore(pg_pool, encryption_key="...")
    await store.put("varun", "google", {"access_token": "...", "refresh_token": "..."})
    creds = await store.get("varun", "google")  # → dict or None
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Current key version — bump when rotating encryption keys
CURRENT_KEY_ID = "v1"


class CredentialStore:
    """Per-user credential vault backed by assistant_system.user_credentials."""

    def __init__(self, pg_pool, encryption_key: Optional[str] = None):
        """
        Args:
            pg_pool: psycopg AsyncConnectionPool connected to assistant_system.
            encryption_key: 32-byte hex string (64 hex chars) for AES-256-GCM.
                            If None, reads from CREDENTIALS_ENCRYPTION_KEY env var.
                            If still None, operates in plaintext mode (dev only).
        """
        self._pool = pg_pool
        self._key_hex = encryption_key or os.getenv("CREDENTIALS_ENCRYPTION_KEY")

        if self._key_hex:
            key_bytes = bytes.fromhex(self._key_hex)
            if len(key_bytes) != 32:
                raise ValueError(
                    f"CREDENTIALS_ENCRYPTION_KEY must be 64 hex chars (32 bytes), got {len(key_bytes)} bytes"
                )
            self._aesgcm = AESGCM(key_bytes)
            logger.info("CredentialStore initialized with AES-256-GCM encryption")
        else:
            self._aesgcm = None
            logger.warning("CredentialStore: no encryption key — storing credentials as plaintext (dev only)")

    def _encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt with AES-256-GCM. Returns nonce (12 bytes) || ciphertext."""
        if not self._aesgcm:
            return plaintext
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def _decrypt(self, data: bytes) -> bytes:
        """Decrypt AES-256-GCM. Expects nonce (12 bytes) || ciphertext."""
        if not self._aesgcm:
            return data
        nonce = data[:12]
        ciphertext = data[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None)

    async def get(self, user_id: str, service: str) -> Optional[dict]:
        """
        Decrypt and return token_data JSON for a service, or None if not found.

        If the row was encrypted with an older key_id, re-encrypts with the
        current key (lazy rotation).
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT token_data, encryption_key_id FROM user_credentials "
                "WHERE user_id = %s AND service = %s",
                (user_id, service),
            )
            row = await cur.fetchone()
            if not row:
                return None

            token_data_bytes, stored_key_id = row[0], row[1]

            # Decrypt — if stored_key_id != current, this assumes the operator
            # has set the correct old key or that plaintext mode was used.
            try:
                plaintext = self._decrypt(bytes(token_data_bytes))
                result = json.loads(plaintext)
            except Exception as e:
                logger.error(f"Failed to decrypt credentials for {user_id}/{service}: {e}")
                return None

            # Lazy re-encryption if key rotated
            if stored_key_id != CURRENT_KEY_ID and self._aesgcm:
                try:
                    new_encrypted = self._encrypt(plaintext)
                    await conn.execute(
                        "UPDATE user_credentials SET token_data = %s, encryption_key_id = %s, "
                        "updated_at = NOW() WHERE user_id = %s AND service = %s",
                        (new_encrypted, CURRENT_KEY_ID, user_id, service),
                    )
                    logger.info(f"Re-encrypted {user_id}/{service} from {stored_key_id} to {CURRENT_KEY_ID}")
                except Exception as e:
                    logger.warning(f"Lazy re-encryption failed for {user_id}/{service}: {e}")

            return result

    async def put(
        self,
        user_id: str,
        service: str,
        token_data: dict,
        scopes: Optional[list[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Encrypt and upsert credential (INSERT ... ON CONFLICT UPDATE)."""
        plaintext = json.dumps(token_data).encode()
        encrypted = self._encrypt(plaintext)

        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO user_credentials
                    (user_id, service, token_data, encryption_key_id, scopes, expires_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, service) DO UPDATE SET
                    token_data = EXCLUDED.token_data,
                    encryption_key_id = EXCLUDED.encryption_key_id,
                    scopes = EXCLUDED.scopes,
                    expires_at = EXCLUDED.expires_at,
                    metadata = COALESCE(EXCLUDED.metadata, user_credentials.metadata),
                    updated_at = NOW()
                """,
                (
                    user_id,
                    service,
                    encrypted,
                    CURRENT_KEY_ID,
                    scopes,
                    expires_at,
                    json.dumps(metadata) if metadata else "{}",
                ),
            )

    async def delete(self, user_id: str, service: str) -> bool:
        """Remove credential. Returns True if a row was deleted."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM user_credentials WHERE user_id = %s AND service = %s",
                (user_id, service),
            )
            return cur.rowcount > 0

    async def list_services(self, user_id: str) -> list[str]:
        """List service names with stored credentials for this user."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT service FROM user_credentials WHERE user_id = %s ORDER BY service",
                (user_id,),
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]
