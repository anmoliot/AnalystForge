"""Data-quality checks over persisted market, fundamental and macro data."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.macro import FxRate, MacroObservation, MacroSeries
from analystforge.api.models.market import Instrument, PriceBar
from analystforge.api.models.news import NewsArticle
from analystforge.api.models.research import FundamentalFact
from analystforge.api.services.coverage import data_coverage

Severity = Literal["error", "warning"]

_STALE_PRICE_DAYS = 7
_STALE_FUNDAMENTAL_DAYS = 730
_STALE_MACRO_DAYS = 400
_STALE_FX_DAYS = 7
_STALE_NEWS_DAYS = 14
_MIN_HISTORY_BARS = 500
_LARGE_MOVE = Decimal("0.5")
_MAX_GAP_DAYS = 10


@dataclass(frozen=True, slots=True)
class QualityFinding:
    code: str
    severity: Severity
    message: str
    instrument: str | None = None
    day: date | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "instrument": self.instrument,
            "day": self.day.isoformat() if self.day else None,
        }


@dataclass(slots=True)
class QualityReport:
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    instruments_checked: int = 0
    bars_checked: int = 0
    findings: list[QualityFinding] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "warning")

    @property
    def status(self) -> str:
        if self.errors:
            return "fail"
        return "warn" if self.warnings else "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at.isoformat(),
            "instruments_checked": self.instruments_checked,
            "bars_checked": self.bars_checked,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": [finding.as_dict() for finding in self.findings],
            "coverage": self.coverage,
        }


async def run_quality_checks(session: AsyncSession) -> QualityReport:
    report = QualityReport()
    today = datetime.now(UTC).date()
    instruments = list(
        (
            await session.scalars(
                select(Instrument)
                .where(Instrument.is_active.is_(True))
                .order_by(Instrument.exchange_code, Instrument.ticker)
            )
        ).all()
    )
    report.instruments_checked = len(instruments)
    labels = {
        instrument.id: f"{instrument.exchange_code}:{instrument.ticker}"
        for instrument in instruments
    }

    bar_rows = (
        await session.execute(
            select(
                PriceBar.instrument_id,
                PriceBar.ts,
                PriceBar.open,
                PriceBar.high,
                PriceBar.low,
                PriceBar.close,
                PriceBar.adjusted_close,
                PriceBar.volume,
            )
            .where(PriceBar.interval == "1d")
            .order_by(PriceBar.instrument_id, PriceBar.ts)
        )
    ).all()
    bars_by_instrument: dict[Any, list[Any]] = defaultdict(list)
    for row in bar_rows:
        bars_by_instrument[row[0]].append(row)
    report.bars_checked = len(bar_rows)

    for instrument in instruments:
        label = labels[instrument.id]
        bars = bars_by_instrument.get(instrument.id, [])
        if not bars:
            report.findings.append(
                QualityFinding("prices_missing", "error", f"{label}: no daily price bars", label)
            )
            continue
        _check_prices(report, label, bars, today)

    facts_by_instrument = {
        instrument_id: (int(count or 0), latest)
        for instrument_id, count, latest in (
            await session.execute(
                select(
                    FundamentalFact.instrument_id,
                    func.count(FundamentalFact.id),
                    func.max(FundamentalFact.period_end),
                ).group_by(FundamentalFact.instrument_id)
            )
        ).all()
    }
    for instrument in instruments:
        if not instrument.cik:
            continue
        facts, latest = facts_by_instrument.get(instrument.id, (0, None))
        label = labels[instrument.id]
        if not facts:
            report.findings.append(
                QualityFinding(
                    "fundamentals_missing",
                    "error",
                    f"{label}: CIK {instrument.cik} has no XBRL facts",
                    label,
                )
            )
        elif latest is not None and latest < today - timedelta(days=_STALE_FUNDAMENTAL_DAYS):
            report.findings.append(
                QualityFinding(
                    "fundamentals_stale",
                    "warning",
                    f"{label}: latest fundamental period ends {latest.isoformat()}",
                    label,
                    latest,
                )
            )

    macro_rows = (
        await session.execute(
            select(
                MacroSeries.code,
                func.count(MacroObservation.day),
                func.max(MacroObservation.day),
            )
            .select_from(MacroSeries)
            .outerjoin(MacroObservation, MacroObservation.series_code == MacroSeries.code)
            .group_by(MacroSeries.code)
            .order_by(MacroSeries.code)
        )
    ).all()
    if not macro_rows:
        report.findings.append(QualityFinding("macro_missing", "error", "no macro series ingested"))
    for code, observations, latest_day in macro_rows:
        if not observations:
            report.findings.append(
                QualityFinding("macro_empty", "error", f"{code}: no observations", code)
            )
        elif latest_day is not None and latest_day < today - timedelta(days=_STALE_MACRO_DAYS):
            report.findings.append(
                QualityFinding(
                    "macro_stale",
                    "warning",
                    f"{code}: latest observation {latest_day.isoformat()}",
                    code,
                    latest_day,
                )
            )

    fx_count, fx_latest, fx_nonpositive = (
        await session.execute(
            select(
                func.count(FxRate.day),
                func.max(FxRate.day),
                func.count().filter(FxRate.rate <= 0),
            )
        )
    ).one()
    if not fx_count:
        report.findings.append(QualityFinding("fx_missing", "error", "no FX rates ingested"))
    else:
        if fx_nonpositive:
            report.findings.append(
                QualityFinding(
                    "fx_nonpositive",
                    "error",
                    f"{fx_nonpositive} FX rates are zero or negative",
                )
            )
        if fx_latest is not None and fx_latest < today - timedelta(days=_STALE_FX_DAYS):
            report.findings.append(
                QualityFinding(
                    "fx_stale",
                    "warning",
                    f"latest FX rate {fx_latest.isoformat()}",
                    day=fx_latest,
                )
            )

    news_count, news_latest = (
        await session.execute(
            select(func.count(NewsArticle.id), func.max(NewsArticle.published_at))
        )
    ).one()
    if not news_count:
        report.findings.append(
            QualityFinding("news_missing", "warning", "no news articles ingested")
        )
    elif news_latest is not None:
        latest_date = news_latest.date() if isinstance(news_latest, datetime) else news_latest
        if latest_date < today - timedelta(days=_STALE_NEWS_DAYS):
            report.findings.append(
                QualityFinding(
                    "news_stale",
                    "warning",
                    f"latest news article {latest_date.isoformat()}",
                    day=latest_date,
                )
            )

    report.coverage = await data_coverage(session)
    return report


def _check_prices(report: QualityReport, label: str, bars: list[Any], today: date) -> None:
    if len(bars) < _MIN_HISTORY_BARS:
        report.findings.append(
            QualityFinding(
                "short_history",
                "warning",
                f"{label}: only {len(bars)} daily bars",
                label,
            )
        )
    last_day = bars[-1][1].date()
    if last_day < today - timedelta(days=_STALE_PRICE_DAYS):
        report.findings.append(
            QualityFinding(
                "prices_stale",
                "error",
                f"{label}: latest bar {last_day.isoformat()}",
                label,
                last_day,
            )
        )

    nonpositive = 0
    inconsistent = 0
    inconsistent_day: date | None = None
    negative_volume = 0
    missing_adjusted = 0
    previous_close: Decimal | None = None
    previous_day: date | None = None
    large_moves: list[tuple[date, Decimal]] = []
    gaps: list[tuple[date, int]] = []

    for _instrument_id, ts, open_, high, low, close, adjusted, volume in bars:
        day = ts.date()
        if min(open_, high, low, close) <= 0 or (adjusted is not None and adjusted <= 0):
            nonpositive += 1
        if high < low or high < max(open_, close) or low > min(open_, close):
            inconsistent += 1
            if inconsistent_day is None:
                inconsistent_day = day
        if volume is not None and volume < 0:
            negative_volume += 1
        if adjusted is None:
            missing_adjusted += 1
        if previous_close is not None and previous_close > 0:
            move = (close - previous_close) / previous_close
            if abs(move) > _LARGE_MOVE:
                large_moves.append((day, move))
        if previous_day is not None:
            gap = (day - previous_day).days
            if gap > _MAX_GAP_DAYS:
                gaps.append((previous_day, gap))
        previous_close = close
        previous_day = day

    if nonpositive:
        report.findings.append(
            QualityFinding(
                "prices_nonpositive",
                "error",
                f"{label}: {nonpositive} bars with non-positive prices",
                label,
            )
        )
    if inconsistent:
        report.findings.append(
            QualityFinding(
                "ohlc_inconsistent",
                "warning",
                f"{label}: {inconsistent} vendor bars violate OHLC bounds (raw values kept)",
                label,
                inconsistent_day,
            )
        )
    if negative_volume:
        report.findings.append(
            QualityFinding(
                "volume_negative",
                "error",
                f"{label}: {negative_volume} bars with negative volume",
                label,
            )
        )
    if missing_adjusted:
        report.findings.append(
            QualityFinding(
                "adjusted_close_missing",
                "warning",
                f"{label}: {missing_adjusted} bars lack an adjusted close",
                label,
            )
        )
    for day, move in large_moves[:5]:
        report.findings.append(
            QualityFinding(
                "large_move",
                "warning",
                f"{label}: close moved {move:.1%} on {day.isoformat()}",
                label,
                day,
            )
        )
    for day, gap in gaps[:5]:
        report.findings.append(
            QualityFinding(
                "date_gap",
                "warning",
                f"{label}: {gap} calendar days without a bar after {day.isoformat()}",
                label,
                day,
            )
        )
