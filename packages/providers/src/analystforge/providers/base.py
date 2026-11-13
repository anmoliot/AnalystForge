"""Provider ports.

Adapters implement one of these interfaces and declare a capability. The rest
of the platform depends only on the ports, never on a vendor SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import StrEnum
from typing import ClassVar

from analystforge.providers.models import (
    CompanyFacts,
    FxRate,
    MacroSeries,
    MacroSeriesSpec,
    NewsItem,
    PriceSeries,
)


class Capability(StrEnum):
    PRICES = "prices"
    FUNDAMENTALS = "fundamentals"
    MACRO = "macro"
    FX = "fx"
    NEWS = "news"


class Provider(ABC):
    name: ClassVar[str]
    capability: ClassVar[Capability]

    def is_configured(self) -> bool:
        """False when required credentials or settings are absent."""
        return True

    @abstractmethod
    async def aclose(self) -> None:
        """Release network resources."""


class PricesProvider(Provider):
    capability = Capability.PRICES

    @abstractmethod
    async def fetch_bars(self, symbol: str, start: date, end: date) -> PriceSeries: ...


class FundamentalsProvider(Provider):
    capability = Capability.FUNDAMENTALS

    @abstractmethod
    async def fetch_company(self, cik: str) -> CompanyFacts: ...


class MacroProvider(Provider):
    capability = Capability.MACRO

    @abstractmethod
    async def fetch_series(self, spec: MacroSeriesSpec, start: date, end: date) -> MacroSeries: ...


class FxProvider(Provider):
    capability = Capability.FX

    @abstractmethod
    async def fetch_rates(self, start: date, end: date, currencies: list[str]) -> list[FxRate]: ...


class NewsProvider(Provider):
    capability = Capability.NEWS

    @abstractmethod
    async def fetch_articles(self, limit: int = 50) -> list[NewsItem]: ...


class HealthState:
    """In-memory health for one adapter, updated by the router."""

    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.last_error: str | None = None
        self.last_success_at: datetime | None = None
        self.last_attempt_at: datetime | None = None
        self.last_latency_ms: int | None = None

    @property
    def status(self) -> str:
        if self.last_attempt_at is None:
            return "unknown"
        return "ok" if self.consecutive_failures == 0 else "error"

    def record_success(self, latency_ms: int, at: datetime) -> None:
        self.consecutive_failures = 0
        self.last_error = None
        self.last_success_at = at
        self.last_attempt_at = at
        self.last_latency_ms = latency_ms

    def record_failure(self, error: str, latency_ms: int, at: datetime) -> None:
        self.consecutive_failures += 1
        self.last_error = error
        self.last_attempt_at = at
        self.last_latency_ms = latency_ms
