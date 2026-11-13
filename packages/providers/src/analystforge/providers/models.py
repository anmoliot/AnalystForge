"""Provider-neutral data transfer objects.

Every adapter returns these types so ingestion code never depends on a vendor
payload. Values that a source does not supply are ``None``; they are never
filled with zero or a placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

ActionType = Literal["split", "dividend"]


@dataclass(frozen=True, slots=True)
class Bar:
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None = None
    volume: int | None = None


@dataclass(frozen=True, slots=True)
class CorporateAction:
    action_type: ActionType
    ex_date: date
    ratio: Decimal | None = None
    amount: Decimal | None = None
    currency: str | None = None


@dataclass(slots=True)
class PriceSeries:
    symbol: str
    bars: list[Bar]
    currency: str | None = None
    exchange: str | None = None
    timezone: str | None = None
    actions: list[CorporateAction] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FundamentalFact:
    taxonomy: str
    concept: str
    unit: str
    value: Decimal
    period_start: date
    period_end: date
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    filed: date
    frame: str | None
    accession: str


@dataclass(frozen=True, slots=True)
class Filing:
    accession: str
    form: str
    filed: date
    period_of_report: date | None
    primary_document: str
    document_url: str


@dataclass(slots=True)
class CompanyFacts:
    cik: str
    entity_name: str
    facts: list[FundamentalFact]
    filings: list[Filing]


@dataclass(frozen=True, slots=True)
class MacroSeriesSpec:
    code: str
    title: str
    units: str
    frequency: str
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class MacroPoint:
    day: date
    value: Decimal | None


@dataclass(slots=True)
class MacroSeries:
    spec: MacroSeriesSpec
    points: list[MacroPoint]


@dataclass(frozen=True, slots=True)
class FxRate:
    day: date
    base: str
    quote: str
    rate: Decimal


@dataclass(frozen=True, slots=True)
class NewsItem:
    url: str
    title: str
    source: str
    summary: str | None = None
    published_at: datetime | None = None
    language: str = "en"
