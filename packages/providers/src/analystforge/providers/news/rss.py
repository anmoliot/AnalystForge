"""RSS/Atom news adapter.

Fetching and parsing are separated so feeds remain testable with recorded XML.
Per-feed failures do not discard articles from healthy feeds; the errors are
exposed in ``last_errors`` and persisted in the ingestion job record.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser

from analystforge.providers.base import NewsProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError, ProviderError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import NewsItem

_CACHE_TTL_SECONDS = 900.0
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class RssNewsProvider(NewsProvider):
    name = "rss"

    def __init__(
        self,
        *,
        feeds: list[str],
        user_agent: str,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._feeds = [feed.strip() for feed in feeds if feed.strip()]
        self._client = ProviderHttpClient(
            self.name,
            user_agent=user_agent,
            cache=cache,
            timeout_seconds=timeout_seconds,
            min_interval_seconds=0.5,
        )
        self.last_errors: list[str] = []

    def is_configured(self) -> bool:
        return bool(self._feeds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_articles(self, limit: int = 50) -> list[NewsItem]:
        if not self._feeds:
            raise ProviderDataError(self.name, "no RSS feeds configured")
        self.last_errors = []
        articles: list[NewsItem] = []
        for feed_url in self._feeds:
            try:
                content = await self._client.get_bytes(feed_url, ttl_seconds=_CACHE_TTL_SECONDS)
            except ProviderError as exc:
                self.last_errors.append(f"{feed_url}: {exc}")
                continue
            articles.extend(self.parse_feed(content, feed_url))
        if not articles:
            detail = "; ".join(self.last_errors) or "feeds returned no entries"
            raise ProviderDataError(self.name, f"no news articles ({detail})")
        by_url: dict[str, NewsItem] = {}
        for article in articles:
            by_url.setdefault(article.url, article)
        ordered = sorted(
            by_url.values(),
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return ordered[:limit]

    @staticmethod
    def parse_feed(content: bytes, feed_url: str) -> list[NewsItem]:
        parsed = feedparser.parse(content)
        source = str(parsed.feed.get("title") or "") or (urlparse(feed_url).hostname or feed_url)
        items: list[NewsItem] = []
        for entry in parsed.entries:
            link = str(entry.get("link") or "").strip()
            title = _clean_text(str(entry.get("title") or ""))
            if not link or not title:
                continue
            summary = _clean_text(str(entry.get("summary") or ""))
            published = _entry_datetime(entry)
            items.append(
                NewsItem(
                    url=link,
                    title=title[:500],
                    source=source[:200],
                    summary=summary[:4000] or None,
                    published_at=published,
                )
            )
        return items


def _entry_datetime(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=UTC)
    return None


def _clean_text(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", value)
    return _WHITESPACE_RE.sub(" ", html.unescape(without_tags)).strip()
