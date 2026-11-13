"""Response caches for provider HTTP calls.

Redis is used when configured (shared across API and worker processes); the
in-process cache is the single-node development fallback. Entries carry an
absolute expiry and are retained after it so the next request can revalidate
with ``If-None-Match`` instead of downloading the payload again.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

_STALE_RETENTION_SECONDS = 7 * 24 * 3600


@dataclass(slots=True)
class CachedResponse:
    content: bytes
    headers: dict[str, str]
    etag: str | None
    expires_at: float


class ResponseCache(Protocol):
    async def get(self, key: str) -> CachedResponse | None: ...

    async def set(
        self, key: str, content: bytes, headers: dict[str, str], etag: str | None, ttl: float
    ) -> None: ...


class MemoryCache:
    def __init__(self, max_entries: int = 2048) -> None:
        self._entries: dict[str, CachedResponse] = {}
        self._max_entries = max_entries

    async def get(self, key: str) -> CachedResponse | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at + _STALE_RETENTION_SECONDS <= time.time():
            self._entries.pop(key, None)
            return None
        return entry

    async def set(
        self, key: str, content: bytes, headers: dict[str, str], etag: str | None, ttl: float
    ) -> None:
        if ttl <= 0:
            return
        if len(self._entries) >= self._max_entries:
            oldest = min(self._entries, key=lambda item: self._entries[item].expires_at)
            self._entries.pop(oldest, None)
        self._entries[key] = CachedResponse(
            content=content,
            headers=headers,
            etag=etag,
            expires_at=time.time() + ttl,
        )


class RedisCache:
    """JSON envelope over a Redis client with ``decode_responses=True``."""

    def __init__(self, client: Any, prefix: str = "af:provider:") -> None:
        self._client = client
        self._prefix = prefix

    async def get(self, key: str) -> CachedResponse | None:
        raw = await self._client.get(self._prefix + key)
        if raw is None:
            return None
        payload = json.loads(raw)
        return CachedResponse(
            content=base64.b64decode(payload["content"]),
            headers=dict(payload["headers"]),
            etag=payload.get("etag"),
            expires_at=float(payload["expires_at"]),
        )

    async def set(
        self, key: str, content: bytes, headers: dict[str, str], etag: str | None, ttl: float
    ) -> None:
        if ttl <= 0:
            return
        payload = json.dumps(
            {
                "content": base64.b64encode(content).decode("ascii"),
                "headers": headers,
                "etag": etag,
                "expires_at": time.time() + ttl,
            }
        )
        retention_ms = int((ttl + _STALE_RETENTION_SECONDS) * 1000)
        await self._client.set(self._prefix + key, payload, px=retention_ms)
