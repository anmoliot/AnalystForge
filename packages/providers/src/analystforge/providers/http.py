"""HTTP client shared by every adapter.

Responsibilities: HTTPS-only requests, a declared User-Agent, response caching
with ETag revalidation, per-provider pacing, bounded retries with deterministic
exponential backoff and honest typed errors. No adapter talks to ``httpx``
directly, so failover and observability behave identically everywhere.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError, ProviderError, ProviderHTTPError

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
logger = logging.getLogger(__name__)


class _RateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = max(0.0, min_interval_seconds)
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._last_call + self._min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


class ProviderHttpClient:
    def __init__(
        self,
        provider: str,
        *,
        user_agent: str,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 30.0,
        max_attempts: int = 4,
        min_interval_seconds: float = 0.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.provider = provider
        self._cache = cache
        self._max_attempts = max(1, max_attempts)
        self._limiter = _RateLimiter(min_interval_seconds)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_bytes(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        ttl_seconds: float = 900.0,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        if not url.startswith("https://"):
            raise ProviderError(self.provider, f"refusing non-HTTPS URL: {url}")
        key = self._cache_key(url, params)
        cached = await self._get_cached(key)
        if cached is not None and cached.expires_at > time.time():
            return cached.content
        request_headers = dict(headers or {})
        if cached and cached.etag:
            request_headers["If-None-Match"] = cached.etag
        last_error: ProviderError | None = None
        for attempt in range(self._max_attempts):
            await self._limiter.acquire()
            try:
                response = await self._client.get(url, params=params, headers=request_headers)
            except httpx.HTTPError as exc:
                last_error = ProviderError(self.provider, f"network error: {exc}", retryable=True)
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                raise last_error from exc
            if response.status_code == 304 and cached is not None:
                await self._set_cached(
                    key,
                    cached.content,
                    dict(response.headers),
                    cached.etag,
                    ttl_seconds,
                )
                return cached.content
            if response.status_code in _RETRYABLE_STATUS:
                last_error = ProviderHTTPError(self.provider, response.status_code, url)
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                raise last_error
            if response.status_code >= 400:
                raise ProviderHTTPError(self.provider, response.status_code, url)
            content = response.content
            await self._set_cached(
                key,
                content,
                dict(response.headers),
                response.headers.get("etag"),
                ttl_seconds,
            )
            return content
        raise last_error or ProviderError(self.provider, "request failed without a response")

    async def _get_cached(self, key: str) -> Any:
        if self._cache is None:
            return None
        try:
            return await self._cache.get(key)
        except Exception:  # cache outages must not break data fetches
            logger.warning("provider.cache_get_failed", extra={"provider": self.provider})
            return None

    async def _set_cached(
        self,
        key: str,
        content: bytes,
        headers: dict[str, str],
        etag: str | None,
        ttl_seconds: float,
    ) -> None:
        if self._cache is None:
            return
        try:
            await self._cache.set(key, content, headers, etag, ttl_seconds)
        except Exception:  # cache outages must not break data fetches
            logger.warning("provider.cache_set_failed", extra={"provider": self.provider})

    async def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        ttl_seconds: float = 900.0,
        headers: dict[str, str] | None = None,
    ) -> str:
        content = await self.get_bytes(url, params=params, ttl_seconds=ttl_seconds, headers=headers)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProviderDataError(self.provider, "response is not valid UTF-8") from exc

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        ttl_seconds: float = 900.0,
        headers: dict[str, str] | None = None,
    ) -> Any:
        text = await self.get_text(url, params=params, ttl_seconds=ttl_seconds, headers=headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderDataError(self.provider, f"invalid JSON from {url}") from exc

    @staticmethod
    def _cache_key(url: str, params: dict[str, Any] | None) -> str:
        query = urlencode(sorted((params or {}).items()))
        return hashlib.sha256(f"{url}?{query}".encode()).hexdigest()

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(0.5 * (2**attempt), 8.0)

    @classmethod
    def _retry_delay(cls, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
        return cls._backoff(attempt)
