"""
Lightweight session cache with TTL expiry.
Operational plumbing — not business logic.
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)


class SessionCache:
    """Thread-safe TTL cache for reducing redundant API calls within a session."""

    def __init__(self, default_ttl: int = 60):
        self._cache: dict = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str):
        """Get cached value if not expired. Returns None on miss."""
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.time() - entry['ts'] < entry['ttl']:
                return entry['value']
            # Expired or missing
            if entry:
                del self._cache[key]
            return None

    def set(self, key: str, value, ttl: int = None):
        """Cache a value with optional custom TTL."""
        with self._lock:
            self._cache[key] = {
                'value': value,
                'ts': time.time(),
                'ttl': ttl or self._default_ttl
            }

    def invalidate(self, key: str):
        """Remove a specific cache entry."""
        with self._lock:
            self._cache.pop(key, None)

    def invalidate_prefix(self, prefix: str):
        """Remove all cache entries whose key starts with prefix."""
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]

    def clear(self):
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            now = time.time()
            total = len(self._cache)
            active = sum(1 for e in self._cache.values() if now - e['ts'] < e['ttl'])
            return {'total_entries': total, 'active_entries': active, 'expired': total - active}


# Singleton instance
cache = SessionCache(default_ttl=60)
