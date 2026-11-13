"""Capability routers with explicit failover and health.

The router tries configured adapters in order, moving recently failed ones to
the back of the queue for a cooldown period. Every attempt is recorded in a
trace so ingestion can persist provider health and surface outages honestly.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from analystforge.providers.base import Capability, HealthState, Provider
from analystforge.providers.errors import AllProvidersFailedError, ProviderError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Attempt:
    provider: str
    status: str
    latency_ms: int | None = None
    error: str | None = None


@dataclass(slots=True)
class FailoverTrace:
    capability: str
    attempts: list[Attempt] = field(default_factory=list)
    provider: str | None = None

    @property
    def failed(self) -> bool:
        return self.provider is None


class ProviderRouter:
    def __init__(
        self,
        capability: Capability,
        providers: Sequence[Provider],
        *,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self.capability = capability
        self.providers = list(providers)
        self._cooldown = cooldown_seconds
        self._health: dict[str, HealthState] = {
            provider.name: HealthState() for provider in self.providers
        }

    def configured(self) -> list[Provider]:
        return [provider for provider in self.providers if provider.is_configured()]

    def health_of(self, provider_name: str) -> HealthState:
        return self._health[provider_name]

    def ordered(self, disabled: frozenset[str]) -> list[Provider]:
        available: list[Provider] = []
        cooling: list[Provider] = []
        for provider in self.providers:
            if provider.name in disabled or not provider.is_configured():
                continue
            health = self._health[provider.name]
            if health.consecutive_failures == 0:
                available.append(provider)
                continue
            last_attempt = health.last_attempt_at
            elapsed = (
                (datetime.now(UTC) - last_attempt).total_seconds()
                if last_attempt is not None
                else self._cooldown
            )
            if elapsed >= self._cooldown:
                available.append(provider)
            else:
                cooling.append(provider)
        return available + cooling

    async def call(
        self,
        method: str,
        *args: Any,
        disabled: frozenset[str] = frozenset(),
        provider_args: dict[str, tuple[Any, ...]] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, FailoverTrace]:
        """Call the first healthy provider configured for this capability.

        ``provider_args`` lets callers pass vendor-specific arguments (for
        example, a price symbol per provider) while keeping one failover path.
        """
        trace = FailoverTrace(capability=str(self.capability))
        failures: list[tuple[str, str]] = []
        for provider in self.ordered(disabled):
            fn: Callable[..., Any] = getattr(provider, method)
            call_args = provider_args.get(provider.name, args) if provider_args else args
            started = time.monotonic()
            try:
                result = await fn(*call_args, **kwargs)
            except ProviderError as exc:
                latency = int((time.monotonic() - started) * 1000)
                self._health[provider.name].record_failure(str(exc), latency, datetime.now(UTC))
                trace.attempts.append(
                    Attempt(provider.name, "error", latency_ms=latency, error=exc.message)
                )
                failures.append((provider.name, exc.message))
                continue
            latency = int((time.monotonic() - started) * 1000)
            self._health[provider.name].record_success(latency, datetime.now(UTC))
            trace.attempts.append(Attempt(provider.name, "ok", latency_ms=latency))
            trace.provider = provider.name
            return result, trace
        raise AllProvidersFailedError(str(self.capability), failures, trace=trace)
