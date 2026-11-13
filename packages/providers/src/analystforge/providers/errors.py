"""Typed provider failures.

The router distinguishes retryable transport/HTTP failures from data errors so
failover decisions are explicit and observable.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for failures raised by a data adapter."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
        self.retryable = retryable


class ProviderNotConfiguredError(ProviderError):
    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(provider, f"not configured: {detail}")


class ProviderHTTPError(ProviderError):
    def __init__(self, provider: str, status_code: int, url: str) -> None:
        super().__init__(
            provider,
            f"HTTP {status_code} from {url}",
            retryable=status_code in {429, 500, 502, 503, 504},
        )
        self.status_code = status_code
        self.url = url


class ProviderDataError(ProviderError):
    """The provider responded, but not with usable data."""


class AllProvidersFailedError(ProviderError):
    def __init__(
        self,
        capability: str,
        failures: list[tuple[str, str]],
        trace: object | None = None,
    ) -> None:
        detail = "; ".join(f"{name}: {message}" for name, message in failures)
        super().__init__("router", f"all {capability} providers failed ({detail})")
        self.capability = capability
        self.failures = failures
        self.trace = trace
