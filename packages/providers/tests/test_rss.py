"""RSS adapter against a recorded SEC press-release feed."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC

import httpx
import pytest
import respx

from analystforge.providers.errors import ProviderDataError
from analystforge.providers.news.rss import RssNewsProvider

_FEED = "https://www.sec.gov/news/pressreleases.rss"
_BROKEN = "https://example.invalid/broken.rss"


def test_parses_recorded_feed(fixture_bytes: Callable[[str], bytes]) -> None:
    items = RssNewsProvider.parse_feed(fixture_bytes("sec_press.rss"), _FEED)
    assert len(items) == 25
    first = items[0]
    assert first.source == "Press Releases"
    assert first.title.startswith("SEC Announces Enforcement Annual Results")
    assert first.url.startswith("https://www.sec.gov/newsroom/press-releases/")
    assert first.published_at is not None
    assert first.published_at.tzinfo is UTC
    assert first.summary
    assert "<" not in first.title


async def test_partial_feed_failure_keeps_healthy_articles(
    fixture_bytes: Callable[[str], bytes],
) -> None:
    provider = RssNewsProvider(feeds=[_FEED, _BROKEN], user_agent="AnalystForge tests")
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_FEED).mock(
                return_value=httpx.Response(200, content=fixture_bytes("sec_press.rss"))
            )
            mock.get(_BROKEN).mock(return_value=httpx.Response(404))
            articles = await provider.fetch_articles(limit=5)
    finally:
        await provider.aclose()

    assert len(articles) == 5
    published = [item.published_at for item in articles]
    assert published == sorted(published, reverse=True)
    assert len(provider.last_errors) == 1
    assert _BROKEN in provider.last_errors[0]
    assert "HTTP 404" in provider.last_errors[0]


async def test_all_feeds_failing_is_a_data_error() -> None:
    provider = RssNewsProvider(feeds=[_BROKEN], user_agent="AnalystForge tests")
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_BROKEN).mock(return_value=httpx.Response(404))
            with pytest.raises(ProviderDataError, match="no news articles"):
                await provider.fetch_articles()
    finally:
        await provider.aclose()
    assert provider.last_errors


async def test_no_feeds_is_not_configured() -> None:
    provider = RssNewsProvider(feeds=[], user_agent="AnalystForge tests")
    assert provider.is_configured() is False
    try:
        with pytest.raises(ProviderDataError, match="no RSS feeds configured"):
            await provider.fetch_articles()
    finally:
        await provider.aclose()


def test_duplicate_links_are_collapsed(fixture_bytes: Callable[[str], bytes]) -> None:
    content = fixture_bytes("sec_press.rss")
    items = RssNewsProvider.parse_feed(content, _FEED)
    urls = [item.url for item in items]
    assert len(urls) == len(set(urls))
