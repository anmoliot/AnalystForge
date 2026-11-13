"""Router failover, cooldown and health behaviour."""

from __future__ import annotations

from datetime import date

import pytest

from analystforge.providers.base import Capability, PricesProvider
from analystforge.providers.errors import AllProvidersFailedError, ProviderDataError
from analystforge.providers.models import Bar, PriceSeries
from analystforge.providers.registry import ProviderConfig, build_registry
from analystforge.providers.router import ProviderRouter


def _series(symbol: str) -> PriceSeries:
    return PriceSeries(
        symbol=symbol,
        currency="USD",
        bars=[
            Bar(
                day=date(2024, 1, 2),
                open=100,
                high=101,
                low=99,
                close=100.5,
            )
        ],
    )


class _Primary(PricesProvider):
    name = "primary"

    def __init__(self, *, fail: bool = True) -> None:
        self.fail = fail
        self.calls = 0

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        self.calls += 1
        if self.fail:
            raise ProviderDataError(self.name, "primary unavailable")
        return _series(symbol)

    async def aclose(self) -> None:
        return None


class _Fallback(PricesProvider):
    name = "fallback"

    def __init__(self) -> None:
        self.calls = 0

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        self.calls += 1
        return _series(symbol)

    async def aclose(self) -> None:
        return None


class _Unconfigured(PricesProvider):
    name = "unconfigured"

    def __init__(self) -> None:
        self.calls = 0

    def is_configured(self) -> bool:
        return False

    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries:
        self.calls += 1
        return _series(symbol)

    async def aclose(self) -> None:
        return None


async def test_failover_demonstrated_when_primary_is_disabled() -> None:
    primary = _Primary()
    fallback = _Fallback()
    router = ProviderRouter(Capability.PRICES, [primary, fallback])

    result, trace = await router.call("fetch_bars", "AAPL", date(2024, 1, 1), date(2024, 1, 31))

    assert result.symbol == "AAPL"
    assert trace.provider == "fallback"
    assert [(attempt.provider, attempt.status) for attempt in trace.attempts] == [
        ("primary", "error"),
        ("fallback", "ok"),
    ]
    assert "primary unavailable" in (trace.attempts[0].error or "")

    disabled_result, disabled_trace = await router.call(
        "fetch_bars",
        "AAPL",
        date(2024, 1, 1),
        date(2024, 1, 31),
        disabled=frozenset({"primary"}),
    )
    assert disabled_result.symbol == "AAPL"
    assert disabled_trace.provider == "fallback"
    assert [attempt.provider for attempt in disabled_trace.attempts] == ["fallback"]
    assert primary.calls == 1
    assert fallback.calls == 2


async def test_health_tracks_success_and_failure() -> None:
    primary = _Primary()
    fallback = _Fallback()
    router = ProviderRouter(Capability.PRICES, [primary, fallback])
    await router.call("fetch_bars", "AAPL", date(2024, 1, 1), date(2024, 1, 31))

    assert router.health_of("primary").status == "error"
    assert router.health_of("primary").consecutive_failures == 1
    assert router.health_of("fallback").status == "ok"
    assert router.health_of("fallback").last_success_at is not None


async def test_failed_provider_moves_behind_healthy_peer_during_cooldown() -> None:
    primary = _Primary()
    fallback = _Fallback()
    router = ProviderRouter(Capability.PRICES, [primary, fallback], cooldown_seconds=300.0)

    await router.call("fetch_bars", "AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert [provider.name for provider in router.ordered(frozenset())] == [
        "fallback",
        "primary",
    ]

    second, trace = await router.call("fetch_bars", "AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert second.symbol == "AAPL"
    assert trace.provider == "fallback"
    assert primary.calls == 1


async def test_all_failures_raise_all_providers_failed() -> None:
    router = ProviderRouter(Capability.PRICES, [_Primary(), _Primary()])
    with pytest.raises(AllProvidersFailedError) as excinfo:
        await router.call("fetch_bars", "AAPL", date(2024, 1, 1), date(2024, 1, 31))
    error = excinfo.value
    assert error.capability == "prices"
    assert len(error.failures) == 2
    assert error.trace is not None
    assert len(error.trace.attempts) == 2  # type: ignore[attr-defined]


async def test_unconfigured_provider_is_skipped() -> None:
    unconfigured = _Unconfigured()
    fallback = _Fallback()
    router = ProviderRouter(Capability.PRICES, [unconfigured, fallback])
    result, trace = await router.call("fetch_bars", "AAPL", date(2024, 1, 1), date(2024, 1, 31))
    assert result.symbol == "AAPL"
    assert trace.provider == "fallback"
    assert unconfigured.calls == 0


def test_registry_rejects_unknown_price_provider() -> None:
    with pytest.raises(ValueError, match="Unknown price provider"):
        build_registry(ProviderConfig(user_agent="tests", prices_order=("nasdaq",)))


def test_registry_primary_map_reports_configuration() -> None:
    registry = build_registry(
        ProviderConfig(user_agent="tests", prices_order=("yahoo", "stooq"), news_feeds=())
    )
    assert registry.primary_map() == {
        "prices": "yahoo",
        "fundamentals": "sec_edgar",
        "macro": "fred",
        "fx": "ecb",
        "news": None,
    }
    snapshot = {row["provider"]: row for row in registry.health_snapshot()}
    assert snapshot["rss"]["configured"] is False
    assert snapshot["yahoo"]["status"] == "unknown"
