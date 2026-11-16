"""Provider registry construction and persisted health views."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.config import Settings
from analystforge.api.models.ops import ProviderHealthRecord
from analystforge.providers.cache import MemoryCache, RedisCache, ResponseCache
from analystforge.providers.registry import (
    ProviderConfig,
    ProviderRegistry,
    build_registry,
)


def build_app_registry(settings: Settings, redis_client: Any | None = None) -> ProviderRegistry:
    cache: ResponseCache
    if redis_client is not None:
        cache = RedisCache(redis_client)
    else:
        cache = MemoryCache()
    return build_registry(
        ProviderConfig(
            user_agent=settings.sec_user_agent,
            prices_order=tuple(settings.price_provider_list),
            news_feeds=tuple(settings.news_feed_list),
            cache=cache,
            timeout_seconds=settings.http_timeout_seconds,
            cooldown_seconds=settings.provider_cooldown_seconds,
            fred_api_key=settings.provider_key("fred"),
        )
    )


async def provider_health(
    session: AsyncSession, registry: ProviderRegistry
) -> list[dict[str, Any]]:
    """Latest persisted attempt per (provider, capability), in-memory fallback."""
    records = list(
        (
            await session.scalars(
                select(ProviderHealthRecord)
                .order_by(ProviderHealthRecord.checked_at.desc())
                .limit(1000)
            )
        ).all()
    )
    persisted: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record.provider, record.capability)
        if key in persisted:
            continue
        persisted[key] = {
            "provider": record.provider,
            "capability": record.capability,
            "status": record.status,
            "latency_ms": record.latency_ms,
            "error": record.error,
            "checked_at": record.checked_at.isoformat() if record.checked_at else None,
            "source": "persisted",
        }
    rows: list[dict[str, Any]] = []
    for snapshot in registry.health_snapshot():
        key = (snapshot["provider"], snapshot["capability"])
        row = dict(persisted.get(key) or {})
        row.update(
            {
                "provider": snapshot["provider"],
                "capability": snapshot["capability"],
                "configured": snapshot["configured"],
            }
        )
        if key not in persisted:
            row.update(
                {
                    "status": snapshot["status"],
                    "latency_ms": snapshot["latency_ms"],
                    "error": snapshot["last_error"],
                    "checked_at": snapshot["last_attempt_at"],
                    "source": "memory",
                }
            )
        rows.append(row)
    rows.sort(key=lambda row: (row["capability"], row["provider"]))
    return rows
