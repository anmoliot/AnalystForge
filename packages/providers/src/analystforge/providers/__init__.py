"""Swappable external data provider adapters for AnalystForge."""

from analystforge.providers.base import (
    Capability,
    FundamentalsProvider,
    FxProvider,
    MacroProvider,
    NewsProvider,
    PricesProvider,
    Provider,
)
from analystforge.providers.cache import MemoryCache, RedisCache, ResponseCache
from analystforge.providers.errors import (
    AllProvidersFailedError,
    ProviderDataError,
    ProviderError,
    ProviderHTTPError,
    ProviderNotConfiguredError,
)
from analystforge.providers.models import (
    Bar,
    CompanyFacts,
    CorporateAction,
    Filing,
    FundamentalFact,
    FxRate,
    MacroPoint,
    MacroSeries,
    MacroSeriesSpec,
    NewsItem,
    PriceSeries,
)
from analystforge.providers.quality import QualityIssue, check_bars
from analystforge.providers.registry import ProviderConfig, ProviderRegistry, build_registry
from analystforge.providers.router import Attempt, FailoverTrace, ProviderRouter

__version__ = "0.1.0"

__all__ = [
    "AllProvidersFailedError",
    "Attempt",
    "Bar",
    "Capability",
    "CompanyFacts",
    "CorporateAction",
    "FailoverTrace",
    "Filing",
    "FundamentalFact",
    "FundamentalsProvider",
    "FxProvider",
    "FxRate",
    "MacroPoint",
    "MacroProvider",
    "MacroSeries",
    "MacroSeriesSpec",
    "MemoryCache",
    "NewsItem",
    "NewsProvider",
    "PriceSeries",
    "PricesProvider",
    "Provider",
    "ProviderConfig",
    "ProviderDataError",
    "ProviderError",
    "ProviderHTTPError",
    "ProviderNotConfiguredError",
    "ProviderRegistry",
    "ProviderRouter",
    "QualityIssue",
    "RedisCache",
    "ResponseCache",
    "build_registry",
    "check_bars",
]
