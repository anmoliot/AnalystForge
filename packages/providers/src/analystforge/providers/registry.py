"""Provider registry: adapters, routing and health snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analystforge.providers.base import Capability, Provider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.fundamentals.sec_edgar import SecEdgarProvider
from analystforge.providers.fx.ecb import EcbFxProvider
from analystforge.providers.macro.fred import FredProvider
from analystforge.providers.news.rss import RssNewsProvider
from analystforge.providers.prices.stooq import StooqProvider
from analystforge.providers.prices.yahoo import YahooPricesProvider
from analystforge.providers.router import ProviderRouter

_PRICE_ADAPTERS = {"yahoo": YahooPricesProvider, "stooq": StooqProvider}


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    user_agent: str
    prices_order: tuple[str, ...] = ("yahoo", "stooq")
    news_feeds: tuple[str, ...] = ()
    cache: ResponseCache | None = None
    timeout_seconds: float = 30.0
    cooldown_seconds: float = 300.0


@dataclass(slots=True)
class ProviderRegistry:
    routers: dict[str, ProviderRouter] = field(default_factory=dict)
    providers: list[Provider] = field(default_factory=list)

    async def call(
        self, capability: Capability | str, method: str, *args: Any, **kwargs: Any
    ) -> tuple[Any, Any]:
        key = str(capability)
        router = self.routers.get(key)
        if router is None:
            raise ValueError(f"unknown provider capability: {key}")
        return await router.call(method, *args, **kwargs)

    def primary_map(self) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for key, router in self.routers.items():
            configured = router.configured()
            result[key] = configured[0].name if configured else None
        return result

    def health_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, router in self.routers.items():
            for provider in router.providers:
                health = router.health_of(provider.name)
                rows.append(
                    {
                        "provider": provider.name,
                        "capability": key,
                        "configured": provider.is_configured(),
                        "status": health.status,
                        "consecutive_failures": health.consecutive_failures,
                        "last_error": health.last_error,
                        "last_success_at": _iso(health.last_success_at),
                        "last_attempt_at": _iso(health.last_attempt_at),
                        "latency_ms": health.last_latency_ms,
                    }
                )
        return rows

    async def aclose(self) -> None:
        seen: set[int] = set()
        for provider in self.providers:
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            await provider.aclose()


def build_registry(config: ProviderConfig) -> ProviderRegistry:
    unknown = [name for name in config.prices_order if name not in _PRICE_ADAPTERS]
    if unknown:
        raise ValueError(
            f"Unknown price provider(s) {unknown}; valid names are {sorted(_PRICE_ADAPTERS)}"
        )
    prices = [
        _PRICE_ADAPTERS[name](
            user_agent=config.user_agent,
            cache=config.cache,
            timeout_seconds=config.timeout_seconds,
        )
        for name in config.prices_order
    ]
    fundamentals: list[Provider] = [
        SecEdgarProvider(
            user_agent=config.user_agent,
            cache=config.cache,
            timeout_seconds=config.timeout_seconds,
        )
    ]
    macro: list[Provider] = [
        FredProvider(
            user_agent=config.user_agent,
            cache=config.cache,
            timeout_seconds=config.timeout_seconds,
        )
    ]
    fx: list[Provider] = [
        EcbFxProvider(
            user_agent=config.user_agent,
            cache=config.cache,
            timeout_seconds=config.timeout_seconds,
        )
    ]
    news: list[Provider] = [
        RssNewsProvider(
            feeds=list(config.news_feeds),
            user_agent=config.user_agent,
            cache=config.cache,
            timeout_seconds=config.timeout_seconds,
        )
    ]
    routers = {
        Capability.PRICES.value: ProviderRouter(
            Capability.PRICES, prices, cooldown_seconds=config.cooldown_seconds
        ),
        Capability.FUNDAMENTALS.value: ProviderRouter(
            Capability.FUNDAMENTALS, fundamentals, cooldown_seconds=config.cooldown_seconds
        ),
        Capability.MACRO.value: ProviderRouter(
            Capability.MACRO, macro, cooldown_seconds=config.cooldown_seconds
        ),
        Capability.FX.value: ProviderRouter(
            Capability.FX, fx, cooldown_seconds=config.cooldown_seconds
        ),
        Capability.NEWS.value: ProviderRouter(
            Capability.NEWS, news, cooldown_seconds=config.cooldown_seconds
        ),
    }
    return ProviderRegistry(routers=routers, providers=[*prices, *fundamentals, *macro, *fx, *news])


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
