"""Shared provider HTTP client: HTTPS, retries, caching and honest failures."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
import respx

from analystforge.providers.cache import CachedResponse, MemoryCache
from analystforge.providers.errors import ProviderDataError, ProviderError, ProviderHTTPError
from analystforge.providers.http import ProviderHttpClient

_URL = "https://api.example.test/data"


def _client(
    cache: Any = None, max_attempts: int = 3
) -> tuple[ProviderHttpClient, httpx.AsyncClient]:
    http = httpx.AsyncClient()
    provider = ProviderHttpClient(
        "test",
        user_agent="AnalystForge tests",
        cache=cache,
        max_attempts=max_attempts,
        client=http,
    )
    return provider, http


async def test_retries_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ProviderHttpClient, "_backoff", staticmethod(lambda attempt: 0.0))
    provider, http = _client()
    try:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.get(_URL).mock(
                side_effect=[httpx.Response(503), httpx.Response(200, content=b"ok")]
            )
            assert await provider.get_bytes(_URL) == b"ok"
            assert route.call_count == 2
    finally:
        await http.aclose()


async def test_retry_exhaustion_raises_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ProviderHttpClient, "_backoff", staticmethod(lambda attempt: 0.0))
    provider, http = _client(max_attempts=2)
    try:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.get(_URL).mock(return_value=httpx.Response(503))
            with pytest.raises(ProviderHTTPError) as excinfo:
                await provider.get_bytes(_URL)
            assert excinfo.value.status_code == 503
            assert route.call_count == 2
    finally:
        await http.aclose()


async def test_client_error_is_not_retried() -> None:
    provider, http = _client()
    try:
        with respx.mock(assert_all_called=True) as mock:
            route = mock.get(_URL).mock(return_value=httpx.Response(404))
            with pytest.raises(ProviderHTTPError) as excinfo:
                await provider.get_bytes(_URL)
            assert excinfo.value.status_code == 404
            assert route.call_count == 1
    finally:
        await http.aclose()


async def test_non_https_url_is_refused() -> None:
    provider, http = _client()
    try:
        with pytest.raises(ProviderError, match="refusing non-HTTPS"):
            await provider.get_bytes("http://api.example.test/data")
    finally:
        await http.aclose()


async def test_cached_response_avoids_network() -> None:
    cache = MemoryCache()
    provider, http = _client(cache)
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.get(_URL).mock(
                return_value=httpx.Response(200, content=b"cached", headers={"etag": '"v1"'})
            )
            assert await provider.get_bytes(_URL) == b"cached"
            assert await provider.get_bytes(_URL) == b"cached"
            assert route.call_count == 1
    finally:
        await http.aclose()


class _StaleCache:
    def __init__(self, content: bytes) -> None:
        self.entry = CachedResponse(
            content=content,
            headers={},
            etag='"stale-etag"',
            expires_at=time.time() - 60,
        )
        self.stored: tuple[bytes, str | None] | None = None

    async def get(self, key: str) -> CachedResponse:
        return self.entry

    async def set(
        self,
        key: str,
        content: bytes,
        headers: dict[str, str],
        etag: str | None,
        ttl: float,
    ) -> None:
        self.stored = (content, etag)


async def test_stale_entry_is_revalidated_with_etag() -> None:
    cache = _StaleCache(b"previous")
    provider, http = _client(cache)
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("if-none-match"))
        return httpx.Response(304)

    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_URL).mock(side_effect=handler)
            assert await provider.get_bytes(_URL, ttl_seconds=600) == b"previous"
    finally:
        await http.aclose()
    assert seen == ['"stale-etag"']
    assert cache.stored == (b"previous", '"stale-etag"')


class _BrokenCache:
    async def get(self, key: str) -> None:
        raise ConnectionError("redis is down")

    async def set(
        self,
        key: str,
        content: bytes,
        headers: dict[str, str],
        etag: str | None,
        ttl: float,
    ) -> None:
        raise ConnectionError("redis is down")


async def test_cache_outage_degrades_to_network() -> None:
    provider, http = _client(_BrokenCache())
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_URL).mock(return_value=httpx.Response(200, content=b"live"))
            assert await provider.get_bytes(_URL) == b"live"
    finally:
        await http.aclose()


async def test_invalid_json_is_a_data_error() -> None:
    provider, http = _client()
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_URL).mock(return_value=httpx.Response(200, content=b"<html>"))
            with pytest.raises(ProviderDataError, match="invalid JSON"):
                await provider.get_json(_URL)
    finally:
        await http.aclose()


def test_retry_delay_honours_header_and_caps() -> None:
    response = httpx.Response(429, headers={"retry-after": "7"})
    assert ProviderHttpClient._retry_delay(response, 0) == 7.0
    capped = httpx.Response(429, headers={"retry-after": "120"})
    assert ProviderHttpClient._retry_delay(capped, 0) == 30.0
    invalid = httpx.Response(429, headers={"retry-after": "soon"})
    assert ProviderHttpClient._retry_delay(invalid, 2) == 2.0


def test_backoff_is_bounded() -> None:
    assert [ProviderHttpClient._backoff(attempt) for attempt in range(6)] == [
        0.5,
        1.0,
        2.0,
        4.0,
        8.0,
        8.0,
    ]
