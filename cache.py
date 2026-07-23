"""
cache.py

Simple caching layer to avoid repeated GitHub API requests for the same
repository. Implemented in-memory for now, but designed with a small,
explicit interface (get/set/delete/clear) so it can be swapped for a
Redis-backed implementation later without touching call sites.
"""

import threading
import time
from typing import Any, Dict, Optional

from config import config


class CacheBackend:
    """Abstract-ish interface. Swap InMemoryCache for a RedisCache later."""

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class InMemoryCache(CacheBackend):
    """
    Thread-safe in-memory TTL cache.

    Storage shape: { key: (expires_at_epoch_seconds, value) }

    NOTE: This cache is process-local. In a multi-worker/multi-process
    deployment (e.g. gunicorn with >1 worker), each worker has its own
    cache. That's acceptable for a hackathon/demo build; swap in
    RedisCache (see below) for shared caching across workers/dynos.
    """

    def __init__(self, default_ttl_seconds: Optional[int] = None):
        self._store: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl_seconds or config.CACHE_TTL_SECONDS

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            expires_at, value = entry
            if time.time() >= expires_at:
                # Expired — clean up and treat as a miss.
                del self._store[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl
        with self._lock:
            self._store[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> Dict[str, Any]:
        """Small helper for debugging / a future /api/cache/stats endpoint."""
        with self._lock:
            now = time.time()
            active = sum(1 for exp, _ in self._store.values() if exp > now)
            return {"total_keys": len(self._store), "active_keys": active}


# -----------------------------------------------------------------------
# Future Redis-backed implementation sketch (not active).
#
# import redis
# import json
#
# class RedisCache(CacheBackend):
#     def __init__(self, redis_url: str, default_ttl_seconds: int):
#         self._client = redis.Redis.from_url(redis_url)
#         self._default_ttl = default_ttl_seconds
#
#     def get(self, key):
#         raw = self._client.get(key)
#         return json.loads(raw) if raw else None
#
#     def set(self, key, value, ttl_seconds=None):
#         ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
#         self._client.set(key, json.dumps(value), ex=ttl)
#
#     def delete(self, key):
#         self._client.delete(key)
#
#     def clear(self):
#         self._client.flushdb()
# -----------------------------------------------------------------------


def build_repo_cache_key(owner: str, repo: str) -> str:
    """Consistent cache key builder for a repository analysis result."""
    return f"repo_analysis:{owner.lower()}/{repo.lower()}"


# Single shared cache instance used across the app.
cache = InMemoryCache()