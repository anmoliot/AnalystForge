"""Portfolio ledger, performance, risk, optimization, and transaction import.

Every number produced here is derived from persisted transactions and price/FX
observations.  When an input is unavailable the service raises
:class:`DataUnavailableError` (HTTP 424) instead of falling back to synthetic data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.errors import DataUnavailableError, ValidationFailedError
from analystforge.api.models.macro import FxRate
from analystforge.api.models.market import Instrument, PriceBar
from analystforge.api.models.portfolio import PortfolioTransaction
from analystforge.quant.attribution import (
    AttributionGroup,
    AttributionMethod,
    AttributionResult,
    brinson_attribution,
)
from analystforge.quant.money import to_decimal
from analystforge.quant.optimization import (
    OptimizationError,
    efficient_frontier,
    max_sharpe,
    mean_covariance,
    min_variance,
    risk_parity,
)
from analystforge.quant.returns import cagr, twr, xirr
from analystforge.quant.risk import (
    alpha,
    beta,
    calmar,
    cvar_historical,
    downside_capture,
    downside_deviation,
    drawdown_series,
    information_ratio,
    max_drawdown,
    max_drawdown_duration,
    risk_contributions,
    sharpe,
    sortino,
    tracking_error,
    upside_capture,
    var_historical,
    var_parametric,
    volatility,
)

ZERO = Decimal("0")
ONE = Decimal("1")
_QTY_EPSILON = Decimal("0.000001")
MIN_RISK_OBSERVATIONS = 5
MIN_OPTIMIZATION_OBSERVATIONS = 20
MIN_BETA_OBSERVATIONS = 20
STALE_PRICE_DAYS = 7
TRANSACTION_TYPES = ("BUY", "SELL", "DIVIDEND", "SPLIT", "FEE")
COST_BASIS_METHODS = ("FIFO", "LIFO", "AVERAGE")


class CostBasisMethod(StrEnum):
    FIFO = "FIFO"
    LIFO = "LIFO"
    AVERAGE = "AVERAGE"


@dataclass
class Lot:
    shares: Decimal
    unit_cost: Decimal
    trade_date: date


@dataclass
class HoldingItem:
    ticker: str
    shares: Decimal
    cost_basis: Decimal
    total_cost: Decimal
    currency: str
    realized_pnl: Decimal = ZERO
    dividends_received: Decimal = ZERO
    fees_paid: Decimal = ZERO
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_pct: float | None = None
    weight: float | None = None
    price_as_of: date | None = None
    price_currency: str | None = None
    fx_rate: Decimal | None = None


@dataclass
class LedgerResult:
    holdings: list[HoldingItem]
    cash_balance: Decimal
    realized_pnl: Decimal
    dividends_received: Decimal
    fees_paid: Decimal
    external_flows: list[tuple[date, Decimal]] = field(default_factory=list)


@dataclass
class PortfolioSnapshot:
    as_of: date
    nav: Decimal
    cash: Decimal
    positions: dict[str, Decimal]


@dataclass
class PriceHistory:
    ticker: str
    instrument_id: uuid.UUID
    currency: str
    series: pd.Series


# ---------------------------------------------------------------------------
# Currency conversion
# ---------------------------------------------------------------------------


async def resolve_fx_rate(
    session: AsyncSession,
    *,
    currency: str,
    base_currency: str,
    day: date,
    explicit_rate: Decimal | float | None = None,
) -> Decimal:
    """Return the rate that converts ``currency`` into ``base_currency``.

    The persisted :class:`FxRate` convention is ``1 base = rate quote`` for the
    pair ``(base, quote)``.  If the direct pair is absent the inverse pair is used.
    A missing rate is a hard error: guessing par would silently corrupt money.
    """
    currency = currency.upper()
    base_currency = base_currency.upper()
    if explicit_rate is not None:
        rate = to_decimal(explicit_rate)
        if not rate.is_finite() or rate <= ZERO:
            raise ValidationFailedError("fx_rate must be a positive finite number.")
        return rate
    if currency == base_currency:
        return ONE

    direct = (
        await session.execute(
            select(FxRate.rate)
            .where(
                FxRate.base == currency,
                FxRate.quote == base_currency,
                FxRate.day <= day,
            )
            .order_by(desc(FxRate.day))
            .limit(1)
        )
    ).scalar_one_or_none()
    if direct is not None:
        return to_decimal(direct)

    inverse = (
        await session.execute(
            select(FxRate.rate)
            .where(
                FxRate.base == base_currency,
                FxRate.quote == currency,
                FxRate.day <= day,
            )
            .order_by(desc(FxRate.day))
            .limit(1)
        )
    ).scalar_one_or_none()
    if inverse is not None and to_decimal(inverse) > ZERO:
        return ONE / to_decimal(inverse)

    raise DataUnavailableError(
        f"No FX rate from {currency} to {base_currency} on or before {day.isoformat()}.",
        details={"currency": currency, "base_currency": base_currency, "day": day.isoformat()},
    )


async def load_fx_series(
    session: AsyncSession,
    currencies: Sequence[str],
    *,
    base_currency: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, pd.Series]:
    """Daily ``currency -> base`` conversion rates built from persisted observations.

    The series is indexed by observation date; callers align it to a trading
    calendar with forward fill.  A currency without any usable observation raises
    :class:`DataUnavailableError` rather than defaulting to parity.
    """
    base = base_currency.upper()
    series: dict[str, pd.Series] = {
        base: pd.Series([1.0], index=pd.DatetimeIndex([pd.Timestamp(date(1970, 1, 1))]))
    }
    for currency in sorted({c.upper() for c in currencies}):
        if currency == base:
            continue
        direct_stmt = select(FxRate.day, FxRate.rate).where(
            FxRate.base == currency, FxRate.quote == base
        )
        inverse_stmt = select(FxRate.day, FxRate.rate).where(
            FxRate.base == base, FxRate.quote == currency
        )
        if start is not None:
            direct_stmt = direct_stmt.where(FxRate.day >= start)
            inverse_stmt = inverse_stmt.where(FxRate.day >= start)
        if end is not None:
            direct_stmt = direct_stmt.where(FxRate.day <= end)
            inverse_stmt = inverse_stmt.where(FxRate.day <= end)
        direct_rows = (await session.execute(direct_stmt.order_by(FxRate.day))).all()
        inverse_rows = (await session.execute(inverse_stmt.order_by(FxRate.day))).all()
        observations: dict[date, float] = {}
        for day, rate in direct_rows:
            value = to_decimal(rate)
            if value > ZERO:
                observations[day] = float(value)
        for day, rate in inverse_rows:
            value = to_decimal(rate)
            if value > ZERO and day not in observations:
                observations[day] = 1.0 / float(value)
        if not observations:
            raise DataUnavailableError(
                f"No FX observations from {currency} to {base}.",
                details={"currency": currency, "base_currency": base},
            )
        ordered_days = sorted(observations)
        series[currency] = pd.Series(
            [observations[day] for day in ordered_days],
            index=pd.DatetimeIndex([pd.Timestamp(day) for day in ordered_days]),
            dtype=float,
        )
    return series


def convert_history_to_base(
    history: PriceHistory,
    fx_series: dict[str, pd.Series],
    *,
    base_currency: str,
) -> PriceHistory:
    """Multiply a local-currency price series by the daily FX rate into base currency."""
    base = base_currency.upper()
    if history.currency.upper() == base:
        return history
    rates = fx_series.get(history.currency.upper())
    if rates is None:
        raise DataUnavailableError(
            f"No FX series from {history.currency} to {base}.",
            details={"ticker": history.ticker, "currency": history.currency},
        )
    aligned = rates.reindex(history.series.index, method="ffill")
    if aligned.isna().any():
        first_missing = history.series.index[aligned.isna()][0]
        raise DataUnavailableError(
            f"No FX rate from {history.currency} to {base} on or before "
            f"{first_missing.date().isoformat()}.",
            details={"ticker": history.ticker, "currency": history.currency},
        )
    converted = history.series * aligned
    return PriceHistory(
        ticker=history.ticker,
        instrument_id=history.instrument_id,
        currency=base,
        series=converted.astype(float),
    )


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def _ordered(transactions: Iterable[PortfolioTransaction]) -> list[PortfolioTransaction]:
    return sorted(
        transactions,
        key=lambda tx: (
            tx.trade_date,
            tx.created_at or datetime.min,
            str(tx.id),
        ),
    )


def _remove_cost(lots: list[Lot], quantity: Decimal, method: CostBasisMethod) -> Decimal:
    """Remove ``quantity`` shares from ``lots`` and return the removed cost."""
    remaining = quantity
    removed = ZERO
    while remaining > _QTY_EPSILON and lots:
        index = 0 if method is CostBasisMethod.FIFO else len(lots) - 1
        lot = lots[index]
        if lot.shares <= remaining + _QTY_EPSILON:
            removed += lot.shares * lot.unit_cost
            remaining -= lot.shares
            lots.pop(index)
        else:
            removed += remaining * lot.unit_cost
            lot.shares -= remaining
            remaining = ZERO
    if remaining > _QTY_EPSILON:
        raise ValidationFailedError(
            "Sell quantity exceeds the shares held; short positions are not supported."
        )
    return removed


@dataclass
class _LedgerState:
    """Incremental transaction replay shared by the ledger and daily NAV.

    Cash never goes negative: a BUY or FEE that exceeds the cash balance records
    only the shortfall as an external contribution (``+`` flow).  SELL proceeds
    are withdrawn immediately (``-`` flow) and therefore leave cash unchanged,
    while dividends stay inside the portfolio.  With this convention the TWR
    identity ``NAV_t = NAV_{t-1} * (1 + r_t) + CF_t`` holds without inventing
    deposits.  See ``docs/DECISIONS.md``.
    """

    method: CostBasisMethod = CostBasisMethod.FIFO
    lots: dict[str, list[Lot]] = field(default_factory=lambda: defaultdict(list))
    currency: dict[str, str] = field(default_factory=dict)
    realized: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    dividends: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    fees: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    cash: Decimal = ZERO
    flows: list[tuple[date, Decimal]] = field(default_factory=list)

    def _spend(self, day: date, amount: Decimal) -> None:
        """Pay ``amount`` from cash first, recording only the shortfall as a flow."""
        if amount <= ZERO:
            return
        if self.cash >= amount:
            self.cash -= amount
            return
        shortfall = amount - self.cash
        self.cash = ZERO
        self.flows.append((day, shortfall))

    def apply(self, tx: PortfolioTransaction) -> None:
        ticker = tx.ticker.upper()
        ttype = tx.transaction_type.upper()
        quantity = to_decimal(tx.quantity)
        price = to_decimal(tx.price)
        fx = to_decimal(tx.fx_rate) if tx.fx_rate is not None else ONE
        commission = to_decimal(tx.commission) * fx
        self.currency[ticker] = tx.currency.upper()

        if ttype == "BUY":
            if quantity <= ZERO:
                raise ValidationFailedError("BUY quantity must be positive.")
            gross = quantity * price * fx + commission
            self.lots[ticker].append(
                Lot(shares=quantity, unit_cost=gross / quantity, trade_date=tx.trade_date)
            )
            self._spend(tx.trade_date, gross)
        elif ttype == "SELL":
            if quantity <= ZERO:
                raise ValidationFailedError("SELL quantity must be positive.")
            held = sum((lot.shares for lot in self.lots[ticker]), ZERO)
            if quantity > held + _QTY_EPSILON:
                raise ValidationFailedError(
                    f"Cannot sell {quantity} {ticker}: only {held} shares are held."
                )
            if self.method is CostBasisMethod.AVERAGE:
                average_cost = (
                    sum((lot.shares * lot.unit_cost for lot in self.lots[ticker]), ZERO) / held
                )
                removed_cost = average_cost * quantity
                remaining = quantity
                while remaining > _QTY_EPSILON and self.lots[ticker]:
                    lot = self.lots[ticker][0]
                    if lot.shares <= remaining + _QTY_EPSILON:
                        remaining -= lot.shares
                        self.lots[ticker].pop(0)
                    else:
                        lot.shares -= remaining
                        remaining = ZERO
                # Reset the surviving lots to the average unit cost so that the
                # remaining total cost stays equal to (original total - sold * average).
                for lot in self.lots[ticker]:
                    lot.unit_cost = average_cost
            else:
                removed_cost = _remove_cost(self.lots[ticker], quantity, self.method)
            net_proceeds = quantity * price * fx - commission
            self.realized[ticker] += net_proceeds - removed_cost
            if net_proceeds >= ZERO:
                # Proceeds leave the portfolio by convention: cash is unchanged.
                self.flows.append((tx.trade_date, -net_proceeds))
            else:
                self._spend(tx.trade_date, -net_proceeds)
        elif ttype == "DIVIDEND":
            if quantity <= ZERO:
                raise ValidationFailedError("DIVIDEND quantity (shares) must be positive.")
            amount = quantity * price * fx - commission
            if amount >= ZERO:
                self.cash += amount
            else:
                self._spend(tx.trade_date, -amount)
            self.dividends[ticker] += amount
        elif ttype == "SPLIT":
            ratio = quantity
            if ratio <= ZERO:
                raise ValidationFailedError("SPLIT ratio must be positive.")
            for lot in self.lots[ticker]:
                lot.shares *= ratio
                lot.unit_cost /= ratio
        elif ttype == "FEE":
            amount = quantity * price * fx + commission
            if amount < ZERO:
                raise ValidationFailedError("FEE amount must be non-negative.")
            self._spend(tx.trade_date, amount)
            self.fees[ticker] += amount
        else:
            raise ValidationFailedError(f"Unsupported transaction type {ttype!r}.")

    def positions(self) -> dict[str, Decimal]:
        return {
            ticker: sum((lot.shares for lot in ticker_lots), ZERO)
            for ticker, ticker_lots in self.lots.items()
            if sum((lot.shares for lot in ticker_lots), ZERO) > _QTY_EPSILON
        }


def _cost_basis_method(value: str) -> CostBasisMethod:
    try:
        return CostBasisMethod(value.upper())
    except ValueError as exc:
        raise ValidationFailedError(
            f"Unsupported cost basis method {value!r}; "
            f"expected one of {', '.join(COST_BASIS_METHODS)}."
        ) from exc


def build_ledger(
    transactions: Sequence[PortfolioTransaction],
    *,
    cost_basis_method: str = "FIFO",
) -> LedgerResult:
    """Replay transactions into open lots, realized P&L, income, and cash.

    Conventions (documented in ``docs/DECISIONS.md``):

    * BUY commission is capitalised into the lot cost and funded cash-first.
    * SELL commission reduces the net proceeds, which are withdrawn.
    * DIVIDEND: ``quantity`` shares x ``price`` per share; commission is withheld.
    * SPLIT: ``quantity`` is the ratio (2 = two-for-one). Price is ignored.
    * FEE: ``quantity * price + commission`` is a cash expense and never a cost basis.
    * All amounts are converted to the portfolio base currency via ``fx_rate``.
    """
    state = _LedgerState(method=_cost_basis_method(cost_basis_method))
    for tx in _ordered(transactions):
        state.apply(tx)

    holdings: list[HoldingItem] = []
    for ticker, ticker_lots in sorted(state.lots.items()):
        open_lots = [lot for lot in ticker_lots if lot.shares > _QTY_EPSILON]
        shares = sum((lot.shares for lot in open_lots), ZERO)
        if shares <= _QTY_EPSILON:
            continue
        total_cost = sum((lot.shares * lot.unit_cost for lot in open_lots), ZERO)
        holdings.append(
            HoldingItem(
                ticker=ticker,
                shares=shares,
                cost_basis=total_cost / shares,
                total_cost=total_cost,
                currency=state.currency.get(ticker, "USD"),
                realized_pnl=state.realized[ticker],
                dividends_received=state.dividends[ticker],
                fees_paid=state.fees[ticker],
            )
        )

    return LedgerResult(
        holdings=holdings,
        cash_balance=state.cash,
        realized_pnl=sum(state.realized.values(), ZERO),
        dividends_received=sum(state.dividends.values(), ZERO),
        fees_paid=sum(state.fees.values(), ZERO),
        external_flows=state.flows,
    )


# Backwards-compatible name used by older callers/tests.
def compute_holdings_fifo(transactions: Sequence[PortfolioTransaction]) -> list[HoldingItem]:
    return build_ledger(transactions, cost_basis_method="FIFO").holdings


# ---------------------------------------------------------------------------
# Market data access
# ---------------------------------------------------------------------------


async def instrument_map(
    session: AsyncSession,
    tickers: Sequence[str],
    *,
    base_currency: str = "USD",
) -> dict[str, Instrument]:
    """Resolve tickers to instruments, preferring the portfolio's currency."""
    wanted = sorted({ticker.upper() for ticker in tickers})
    if not wanted:
        return {}
    rows = (
        (await session.execute(select(Instrument).where(Instrument.ticker.in_(wanted))))
        .scalars()
        .all()
    )
    resolved: dict[str, Instrument] = {}
    for instrument in sorted(
        rows,
        key=lambda item: (item.currency != base_currency.upper(), item.ticker, str(item.id)),
    ):
        resolved.setdefault(instrument.ticker.upper(), instrument)
    return resolved


async def load_price_histories(
    session: AsyncSession,
    tickers: Sequence[str],
    *,
    base_currency: str = "USD",
    start: date | None = None,
    end: date | None = None,
) -> tuple[dict[str, PriceHistory], list[str], dict[str, Instrument]]:
    """Load adjusted closes for ``tickers``.

    Returns the histories that exist, the missing tickers, and the resolved
    instrument map.  Callers decide whether missing data is fatal.
    """
    instruments = await instrument_map(session, tickers, base_currency=base_currency)
    histories: dict[str, PriceHistory] = {}
    missing: list[str] = []
    for ticker in sorted({t.upper() for t in tickers}):
        instrument = instruments.get(ticker)
        if instrument is None:
            missing.append(ticker)
            continue
        stmt = select(PriceBar.ts, PriceBar.close, PriceBar.adjusted_close).where(
            PriceBar.instrument_id == instrument.id,
            PriceBar.interval == "1d",
        )
        if start is not None:
            stmt = stmt.where(PriceBar.ts >= datetime.combine(start, datetime.min.time()))
        if end is not None:
            stmt = stmt.where(
                PriceBar.ts < datetime.combine(end + timedelta(days=1), datetime.min.time())
            )
        rows = (await session.execute(stmt.order_by(PriceBar.ts))).all()
        if not rows:
            missing.append(ticker)
            continue
        index = pd.DatetimeIndex([row[0] for row in rows]).normalize()
        values = [
            float(row[2] if row[2] is not None else row[1])
            for row in rows
        ]
        series = pd.Series(values, index=index, name=ticker, dtype=float)
        series = series[~series.index.duplicated(keep="last")].sort_index()
        histories[ticker] = PriceHistory(
            ticker=ticker,
            instrument_id=instrument.id,
            currency=instrument.currency,
            series=series,
        )
    return histories, missing, instruments


async def latest_prices(
    session: AsyncSession,
    tickers: Sequence[str],
    *,
    base_currency: str = "USD",
) -> dict[str, tuple[Decimal, date, str, Decimal]]:
    """Latest close per ticker, converted to ``base_currency``.

    Returns ``ticker -> (price_in_base, price_date, price_currency, fx_rate)``.
    """
    result: dict[str, tuple[Decimal, date, str, Decimal]] = {}
    instruments = await instrument_map(session, tickers, base_currency=base_currency)
    for ticker in sorted({t.upper() for t in tickers}):
        instrument = instruments.get(ticker)
        if instrument is None:
            continue
        row = (
            await session.execute(
                select(PriceBar.ts, PriceBar.close, PriceBar.adjusted_close)
                .where(PriceBar.instrument_id == instrument.id, PriceBar.interval == "1d")
                .order_by(desc(PriceBar.ts))
                .limit(1)
            )
        ).first()
        if row is None:
            continue
        day = row[0].date()
        raw = to_decimal(row[2] if row[2] is not None else row[1])
        rate = await resolve_fx_rate(
            session, currency=instrument.currency, base_currency=base_currency, day=day
        )
        result[ticker] = (raw * rate, day, instrument.currency, rate)
    return result


async def enrich_holdings_with_prices(
    session: AsyncSession,
    holdings: list[HoldingItem],
    *,
    base_currency: str = "USD",
) -> list[HoldingItem]:
    """Attach latest market prices, market values, P&L, and weights."""
    if not holdings:
        return []
    prices = await latest_prices(session, [h.ticker for h in holdings], base_currency=base_currency)
    priced_total = ZERO
    for holding in holdings:
        quote = prices.get(holding.ticker)
        if quote is None:
            holding.current_price = None
            holding.market_value = None
            holding.unrealized_pnl = None
            holding.unrealized_pnl_pct = None
            holding.weight = None
            continue
        price_base, day, price_currency, rate = quote
        holding.current_price = price_base
        holding.price_as_of = day
        holding.price_currency = price_currency
        holding.fx_rate = rate
        holding.market_value = holding.shares * price_base
        holding.unrealized_pnl = holding.market_value - holding.total_cost
        holding.unrealized_pnl_pct = (
            float(holding.unrealized_pnl / holding.total_cost)
            if holding.total_cost > ZERO
            else None
        )
        priced_total += holding.market_value
    if priced_total > ZERO:
        for holding in holdings:
            if holding.market_value is not None:
                holding.weight = float(holding.market_value / priced_total)
    return holdings


# ---------------------------------------------------------------------------
# Daily NAV / performance
# ---------------------------------------------------------------------------


def _price_on(series: pd.Series[float], day: date) -> float | None:
    index = series.index.searchsorted(pd.Timestamp(day))
    if index <= 0:
        return None
    timestamp = series.index[index - 1]
    if (pd.Timestamp(day) - timestamp).days > STALE_PRICE_DAYS:
        return None
    return float(series.iloc[index - 1])


def build_daily_nav(
    transactions: Sequence[PortfolioTransaction],
    histories: dict[str, PriceHistory],
    *,
    cost_basis_method: str = "FIFO",
) -> list[PortfolioSnapshot]:
    """Value the ledger at each date covered by its price history.

    Holdings are marked at the latest adjusted close on or before each date.  A
    held ticker with no price within :data:`STALE_PRICE_DAYS` makes the valuation
    unavailable for that date (and the first such date is reported).  Only tickers
    actually bought need price history: cash-only transactions such as fees or
    dividends do not require a tradable instrument.
    """
    ordered = _ordered(transactions)
    if not ordered:
        return []
    traded = sorted(
        {
            tx.ticker.upper()
            for tx in ordered
            if tx.transaction_type.upper() in {"BUY", "SELL", "SPLIT"}
        }
    )
    for ticker in traded:
        if ticker not in histories:
            raise DataUnavailableError(
                f"No daily price history is available for {ticker}.",
                details={"ticker": ticker},
            )

    calendar_points = {pd.Timestamp(tx.trade_date) for tx in ordered}
    for ticker in traded:
        calendar_points |= set(histories[ticker].series.index)
    first_tx = ordered[0].trade_date
    calendar = sorted(day for day in calendar_points if day.date() >= first_tx)
    if not calendar:
        raise DataUnavailableError(
            "Transaction dates do not overlap the available price history."
        )

    state = _LedgerState(method=_cost_basis_method(cost_basis_method))
    index = 0
    snapshots: list[PortfolioSnapshot] = []
    for timestamp in calendar:
        day = timestamp.date()
        while index < len(ordered) and ordered[index].trade_date <= day:
            state.apply(ordered[index])
            index += 1

        positions = state.positions()
        nav = state.cash
        for ticker, shares in positions.items():
            history = histories.get(ticker)
            price = None if history is None else _price_on(history.series, day)
            if price is None:
                raise DataUnavailableError(
                    f"No price for {ticker} within {STALE_PRICE_DAYS} days of {day.isoformat()}.",
                    details={"ticker": ticker, "day": day.isoformat()},
                )
            nav += shares * to_decimal(price)
        snapshots.append(
            PortfolioSnapshot(as_of=day, nav=nav, cash=state.cash, positions=positions)
        )
    return snapshots


def compute_performance(
    snapshots: Sequence[PortfolioSnapshot],
    external_flows: Sequence[tuple[date, Decimal]],
) -> dict[str, Any]:
    """TWR, XIRR, CAGR and drawdown from a dated NAV series."""
    if len(snapshots) < 2:
        raise DataUnavailableError(
            "At least two daily NAV observations are required to compute performance."
        )
    nav_series = [(snapshot.as_of, snapshot.nav) for snapshot in snapshots]
    nav_prices = pd.Series(
        [float(snapshot.nav) for snapshot in snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(snapshot.as_of) for snapshot in snapshots]),
        dtype=float,
    )
    nav_dates = [snapshot.as_of for snapshot in snapshots]
    flow_map: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for day, amount in external_flows:
        position = bisect_left(nav_dates, day)
        if position >= len(nav_dates):
            raise DataUnavailableError(
                f"Cash flow on {day.isoformat()} occurs after the last NAV observation."
            )
        flow_map[nav_dates[position]] += amount
    flows = sorted(flow_map.items())

    twr_value: Decimal | None = None
    twr_error: str | None = None
    try:
        twr_value = twr(flows, nav_series)
    except ValueError as exc:
        twr_error = str(exc)

    xirr_value: Decimal | None = None
    xirr_error: str | None = None
    investor_flows = sorted(
        [(day, -amount) for day, amount in flow_map.items()]
        + [(snapshots[-1].as_of, snapshots[-1].nav)]
    )
    try:
        xirr_value = xirr(investor_flows)
    except ValueError as exc:
        xirr_error = str(exc)

    returns = nav_prices.pct_change().dropna()
    drawdowns = drawdown_series(nav_prices)
    return {
        "as_of": snapshots[-1].as_of.isoformat(),
        "start": snapshots[0].as_of.isoformat(),
        "observations": len(snapshots),
        "nav": float(snapshots[-1].nav),
        "cash": float(snapshots[-1].cash),
        "twr": float(twr_value) if twr_value is not None else None,
        "twr_error": twr_error,
        "xirr": float(xirr_value) if xirr_value is not None else None,
        "xirr_error": xirr_error,
        "cagr": round(cagr(nav_prices), 8) if len(nav_prices) >= 2 else None,
        "max_drawdown": round(max_drawdown(nav_prices), 8),
        "max_drawdown_duration": max_drawdown_duration(nav_prices),
        "volatility": round(volatility(returns), 8),
        "series": [
            {
                "date": snapshot.as_of.isoformat(),
                "nav": float(snapshot.nav),
                "cash": float(snapshot.cash),
                "drawdown": round(float(drawdowns.iloc[position]), 8),
            }
            for position, snapshot in enumerate(snapshots)
        ],
        "formula": (
            "NAV_t = cash_t + sum(shares_i,t * close_i,t); "
            "TWR = prod((NAV_t - CF_t) / NAV_{t-1}) - 1; "
            "XIRR solves sum(CF_i / (1+r)^(days_i/365)) = 0"
        ),
    }


# ---------------------------------------------------------------------------
# Risk analytics
# ---------------------------------------------------------------------------


def _benchmark_returns(
    snapshots: Sequence[PortfolioSnapshot],
    benchmark: PriceHistory | None,
) -> pd.Series[float] | None:
    if benchmark is None or len(snapshots) < 2:
        return None
    index = pd.DatetimeIndex([pd.Timestamp(snapshot.as_of) for snapshot in snapshots])
    aligned = benchmark.series.reindex(index, method="ffill")
    if aligned.isna().any():
        return None
    return aligned.pct_change().dropna()


def compute_risk_metrics(
    snapshots: Sequence[PortfolioSnapshot],
    *,
    benchmark: PriceHistory | None = None,
    risk_free_rate: float = 0.04,
) -> dict[str, Any]:
    """Risk metrics with explicit provenance for every annualisation choice."""
    if len(snapshots) < MIN_RISK_OBSERVATIONS:
        raise DataUnavailableError(
            f"At least {MIN_RISK_OBSERVATIONS} daily NAV observations are required "
            f"(found {len(snapshots)})."
        )
    nav_prices = pd.Series(
        [float(snapshot.nav) for snapshot in snapshots],
        index=pd.DatetimeIndex([pd.Timestamp(snapshot.as_of) for snapshot in snapshots]),
        dtype=float,
    )
    returns = nav_prices.pct_change().dropna()
    if len(returns) < MIN_RISK_OBSERVATIONS - 1:
        raise DataUnavailableError("Not enough return observations for risk metrics.")

    benchmark_returns = _benchmark_returns(snapshots, benchmark)
    portfolio_returns = returns.copy()
    portfolio_returns.index = nav_prices.index[1:]
    benchmark_metrics: dict[str, Any] = {
        "status": "unavailable" if benchmark_returns is None else "ok",
        "reason": None if benchmark_returns is not None else "benchmark price history missing",
        "beta": None,
        "alpha": None,
        "tracking_error": None,
        "information_ratio": None,
        "upside_capture": None,
        "downside_capture": None,
    }
    if benchmark_returns is not None:
        aligned_portfolio = returns.reindex(benchmark_returns.index)
        if aligned_portfolio.notna().sum() >= MIN_BETA_OBSERVATIONS:
            aligned_portfolio = aligned_portfolio.dropna()
            benchmark_returns = benchmark_returns.loc[aligned_portfolio.index]
            benchmark_metrics.update(
                {
                    "status": "ok",
                    "beta": _round(beta(aligned_portfolio, benchmark_returns), 6),
                    "alpha": _round(
                        alpha(aligned_portfolio, benchmark_returns, risk_free=risk_free_rate), 6
                    ),
                    "tracking_error": _round(
                        tracking_error(aligned_portfolio, benchmark_returns), 6
                    ),
                    "information_ratio": _round(
                        information_ratio(aligned_portfolio, benchmark_returns), 6
                    ),
                    "upside_capture": _round(upside_capture(aligned_portfolio, benchmark_returns), 6),
                    "downside_capture": _round(
                        downside_capture(aligned_portfolio, benchmark_returns), 6
                    ),
                }
            )
        else:
            benchmark_metrics["reason"] = (
                f"fewer than {MIN_BETA_OBSERVATIONS} overlapping benchmark observations"
            )

    drawdowns = drawdown_series(nav_prices)
    worst_index = drawdowns.idxmin()
    return {
        "as_of": snapshots[-1].as_of.isoformat(),
        "start": snapshots[0].as_of.isoformat(),
        "observations": len(snapshots),
        "annualization_periods": 252,
        "risk_free_rate": risk_free_rate,
        "volatility": _round(volatility(returns), 8),
        "downside_deviation": _round(downside_deviation(returns), 8),
        "sharpe": _round(sharpe(returns, risk_free=risk_free_rate), 6),
        "sortino": _round(sortino(returns, risk_free=risk_free_rate, mar=0.0), 6),
        "calmar": _round(calmar(returns), 6),
        "max_drawdown": _round(max_drawdown(nav_prices), 8),
        "max_drawdown_duration": max_drawdown_duration(nav_prices),
        "max_drawdown_date": None if worst_index is None else str(worst_index.date()),
        "var_95_hist": _round(var_historical(returns, confidence=0.95), 8),
        "var_95_param": _round(var_parametric(returns, confidence=0.95), 8),
        "cvar_95": _round(cvar_historical(returns, confidence=0.95), 8),
        "benchmark": benchmark_metrics,
        "drawdown_series": [
            {"date": str(index.date()), "drawdown": round(float(value), 8)}
            for index, value in drawdowns.items()
        ],
        "returns": [
            {"date": str(index.date()), "return": round(float(value), 8)}
            for index, value in returns.items()
        ],
        "formula": (
            "vol = std(r, ddof=1) * sqrt(252); Sharpe = mean(r - rf/252)/std(r - rf/252)*sqrt(252); "
            "Sortino = (annual return - rf)/downside deviation; "
            "VaR_95 = -percentile(r, 5); CVaR_95 = -mean(r | r <= percentile(r,5))"
        ),
    }


def _round(value: float | None, places: int) -> float | None:
    return None if value is None else round(float(value), places)


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------


def returns_matrix(
    histories: dict[str, PriceHistory],
    tickers: Sequence[str],
) -> pd.DataFrame:
    """Aligned simple returns for the requested tickers."""
    missing = [ticker for ticker in tickers if ticker not in histories]
    if missing:
        raise DataUnavailableError(
            "Optimization requires daily prices for every holding.",
            details={"missing_tickers": missing},
        )
    frame = pd.DataFrame({ticker: histories[ticker].series for ticker in tickers}).sort_index()
    frame = frame.ffill().dropna()
    if len(frame) < MIN_OPTIMIZATION_OBSERVATIONS + 1:
        raise DataUnavailableError(
            f"Optimization requires at least {MIN_OPTIMIZATION_OBSERVATIONS + 1} aligned "
            f"price observations (found {len(frame)}).",
            details={"observations": len(frame)},
        )
    returns = frame.pct_change().dropna()
    if len(returns) < MIN_OPTIMIZATION_OBSERVATIONS:
        raise DataUnavailableError(
            f"Optimization requires at least {MIN_OPTIMIZATION_OBSERVATIONS} return "
            f"observations (found {len(returns)})."
        )
    return returns


def optimize_weights(
    returns_df: pd.DataFrame,
    *,
    objective: str = "max_sharpe",
    risk_free_rate: float = 0.04,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> dict[str, Any]:
    """Run the quant solver for ``objective`` and return traceable output."""
    if objective not in {"max_sharpe", "min_variance", "risk_parity"}:
        raise ValidationFailedError(
            "objective must be one of max_sharpe, min_variance, risk_parity."
        )
    tickers = [str(column) for column in returns_df.columns]
    try:
        means, covariance = mean_covariance(returns_df)
        if objective == "max_sharpe":
            result = max_sharpe(
                means,
                covariance,
                risk_free_rate=risk_free_rate,
                min_weight=min_weight,
                max_weight=max_weight,
            )
        elif objective == "min_variance":
            result = min_variance(
                means,
                covariance,
                risk_free_rate=risk_free_rate,
                min_weight=min_weight,
                max_weight=max_weight,
            )
        else:
            result = risk_parity(
                covariance,
                expected_returns=means,
                risk_free_rate=risk_free_rate,
            )
        frontier = efficient_frontier(
            means,
            covariance,
            points=15,
            risk_free_rate=risk_free_rate,
            min_weight=min_weight,
            max_weight=max_weight,
        )
        contributions = risk_contributions(list(result.weights), covariance)
    except OptimizationError as exc:
        raise DataUnavailableError(f"Portfolio optimization failed: {exc}") from exc

    return {
        "objective": objective,
        "tickers": tickers,
        "weights": {
            ticker: round(float(weight), 8)
            for ticker, weight in zip(tickers, result.weights, strict=True)
        },
        "expected_return": _round(result.expected_return, 8),
        "expected_volatility": _round(result.volatility, 8),
        "sharpe": _round(result.sharpe, 6),
        "solver": result.solver,
        "status": result.status,
        "observations": len(returns_df),
        "as_of": str(returns_df.index[-1].date()),
        "risk_contributions": {
            ticker: round(float(contribution), 8)
            for ticker, contribution in zip(tickers, contributions, strict=True)
        },
        "frontier": [
            {
                "target_return": round(float(point.target_return), 8),
                "volatility": round(float(point.result.volatility), 8),
                "expected_return": _round(point.result.expected_return, 8),
                "sharpe": _round(point.result.sharpe, 6),
            }
            for point in frontier
        ],
        "formula": (
            "mu = mean(R) * 252; Sigma = cov(R, ddof=1) * 252; "
            "max Sharpe = max (w'mu - rf) / sqrt(w'Sigma w) s.t. sum(w)=1, w in bounds"
        ),
    }


def current_weights(holdings: Sequence[HoldingItem]) -> dict[str, float]:
    total = sum(
        (holding.market_value for holding in holdings if holding.market_value is not None),
        ZERO,
    )
    if total <= ZERO:
        return {}
    return {
        holding.ticker: float(holding.market_value / total)
        for holding in holdings
        if holding.market_value is not None
    }


# ---------------------------------------------------------------------------
# Stress testing
# ---------------------------------------------------------------------------


STRESS_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "name": "Global Financial Crisis",
        "start": date(2008, 9, 12),
        "end": date(2009, 3, 9),
        "description": "Lehman collapse through the March 2009 equity trough.",
    },
    {
        "name": "COVID-19 liquidity shock",
        "start": date(2020, 2, 19),
        "end": date(2020, 3, 23),
        "description": "Pandemic lockdown sell-off.",
    },
    {
        "name": "2022 rate shock",
        "start": date(2022, 1, 3),
        "end": date(2022, 10, 12),
        "description": "Inflation and rapid central-bank tightening.",
    },
    {
        "name": "2018 Q4 sell-off",
        "start": date(2018, 9, 20),
        "end": date(2018, 12, 24),
        "description": "Growth scare and trade-war drawdown.",
    },
)


def _window_return(series: pd.Series[float], start: date, end: date) -> float | None:
    start_index = series.index.searchsorted(pd.Timestamp(start))
    end_index = series.index.searchsorted(pd.Timestamp(end), side="right") - 1
    if start_index >= len(series) or end_index <= start_index:
        return None
    if (series.index[start_index].date() - start).days > 10:
        return None
    if (end - series.index[end_index].date()).days > 10:
        return None
    return float(series.iloc[end_index] / series.iloc[start_index] - 1.0)


def execute_stress_tests(
    holdings: Sequence[HoldingItem],
    total_value: Decimal,
    *,
    benchmark: PriceHistory | None = None,
    nav_snapshots: Sequence[PortfolioSnapshot] = (),
    portfolio_beta: float | None = None,
) -> list[dict[str, Any]]:
    """Beta-scaled historical benchmark shocks.

    Each scenario uses the realised benchmark return over a documented crisis
    window and scales it by the portfolio's CAPM beta.  Scenarios whose data is
    not covered are reported as ``unavailable`` with a reason; no shock is invented.
    """
    results: list[dict[str, Any]] = []
    if benchmark is None:
        raise DataUnavailableError(
            "Stress testing requires benchmark price history.",
            details={"benchmark": "missing"},
        )
    if portfolio_beta is None:
        if len(nav_snapshots) < MIN_BETA_OBSERVATIONS:
            raise DataUnavailableError(
                "Stress testing requires enough NAV history to estimate portfolio beta."
            )
        benchmark_returns = _benchmark_returns(nav_snapshots, benchmark)
        if benchmark_returns is None:
            raise DataUnavailableError("Benchmark prices do not overlap the portfolio NAV history.")
        nav_prices = pd.Series(
            [float(snapshot.nav) for snapshot in nav_snapshots],
            index=pd.DatetimeIndex([pd.Timestamp(snapshot.as_of) for snapshot in nav_snapshots]),
            dtype=float,
        )
        portfolio_returns = nav_prices.pct_change().dropna().reindex(benchmark_returns.index).dropna()
        benchmark_returns = benchmark_returns.loc[portfolio_returns.index]
        if len(portfolio_returns) < MIN_BETA_OBSERVATIONS:
            raise DataUnavailableError("Not enough overlapping observations to estimate beta.")
        portfolio_beta = beta(portfolio_returns, benchmark_returns)
    if portfolio_beta is None:
        raise DataUnavailableError("Portfolio beta is undefined against the benchmark.")

    for scenario in STRESS_SCENARIOS:
        benchmark_return = _window_return(benchmark.series, scenario["start"], scenario["end"])
        if benchmark_return is None:
            results.append(
                {
                    **scenario,
                    "start": scenario["start"].isoformat(),
                    "end": scenario["end"].isoformat(),
                    "status": "unavailable",
                    "reason": "benchmark price history does not cover this window",
                    "beta": round(float(portfolio_beta), 6),
                    "benchmark_return": None,
                    "shock_pct": None,
                    "projected_loss": None,
                    "post_shock_value": None,
                }
            )
            continue
        shock = float(portfolio_beta) * benchmark_return
        projected_loss = total_value * to_decimal(shock)
        results.append(
            {
                **scenario,
                "start": scenario["start"].isoformat(),
                "end": scenario["end"].isoformat(),
                "status": "ok",
                "reason": None,
                "beta": round(float(portfolio_beta), 6),
                "benchmark_return": round(benchmark_return, 8),
                "shock_pct": round(shock, 8),
                "projected_loss": float(projected_loss),
                "post_shock_value": float(total_value + projected_loss),
                "formula": "portfolio shock = beta * benchmark window return",
            }
        )
    return results


# ---------------------------------------------------------------------------
# Brinson attribution
# ---------------------------------------------------------------------------


def compute_sector_attribution(
    holdings: Sequence[HoldingItem],
    histories: dict[str, PriceHistory],
    *,
    sectors: dict[str, str],
    benchmark_groups: Sequence[dict[str, Any]],
    start: date,
    end: date,
    method: str = "bhb",
) -> dict[str, Any]:
    """Brinson attribution using caller-supplied benchmark sector data.

    Portfolio sector weights/returns come from holdings and observed prices; the
    benchmark weights/returns are explicit inputs so no benchmark constituency is
    fabricated.
    """
    if not holdings:
        raise DataUnavailableError("Attribution requires at least one open holding.")
    if not benchmark_groups:
        raise ValidationFailedError("benchmark_groups must not be empty.")

    portfolio_by_sector: dict[str, list[tuple[Decimal, float]]] = defaultdict(list)
    for holding in holdings:
        history = histories.get(holding.ticker)
        if history is None:
            raise DataUnavailableError(f"No price history for {holding.ticker}.")
        if holding.market_value is None:
            raise DataUnavailableError(
                f"Attribution requires a market price for {holding.ticker}.",
                details={"ticker": holding.ticker},
            )
        sector = sectors.get(holding.ticker, "Unclassified")
        value = holding.market_value
        start_index = history.series.index.searchsorted(pd.Timestamp(start))
        end_index = history.series.index.searchsorted(pd.Timestamp(end), side="right") - 1
        if start_index >= len(history.series) or end_index <= start_index:
            raise DataUnavailableError(
                f"Price history for {holding.ticker} does not cover the attribution window."
            )
        holding_return = float(
            history.series.iloc[end_index] / history.series.iloc[start_index] - 1.0
        )
        portfolio_by_sector[sector].append((value, holding_return))

    total_value = sum((value for rows in portfolio_by_sector.values() for value, _ in rows), ZERO)
    if total_value <= ZERO:
        raise DataUnavailableError("Attribution requires priced holdings.")
    portfolio_weights: dict[str, Decimal] = {}
    portfolio_returns: dict[str, Decimal] = {}
    for sector, rows in portfolio_by_sector.items():
        sector_value = sum((value for value, _ in rows), ZERO)
        portfolio_weights[sector] = sector_value / total_value
        portfolio_returns[sector] = sum(
            (to_decimal(ret) * value for value, ret in rows), ZERO
        ) / sector_value

    benchmark_by_name = {str(row["name"]): row for row in benchmark_groups}
    names = sorted(set(portfolio_by_sector) | set(benchmark_by_name))
    groups = [
        AttributionGroup(
            name=name,
            portfolio_weight=portfolio_weights.get(name, ZERO),
            benchmark_weight=to_decimal(benchmark_by_name.get(name, {}).get("weight", 0)),
            portfolio_return=portfolio_returns.get(name, ZERO),
            benchmark_return=to_decimal(benchmark_by_name.get(name, {}).get("return", 0)),
        )
        for name in names
    ]
    try:
        result: AttributionResult = brinson_attribution(groups, method)
    except ValueError as exc:
        raise ValidationFailedError(f"Attribution inputs do not reconcile: {exc}") from exc
    return {
        "method": str(result.method),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "portfolio_return": float(result.portfolio_return),
        "benchmark_return": float(result.benchmark_return),
        "active_return": float(result.active_return),
        "allocation": float(result.allocation),
        "selection": float(result.selection),
        "interaction": float(result.interaction),
        "rows": [
            {
                "group": row.group,
                "portfolio_weight": float(row.portfolio_weight),
                "benchmark_weight": float(row.benchmark_weight),
                "portfolio_return": float(row.portfolio_return),
                "benchmark_return": float(row.benchmark_return),
                "allocation": float(row.allocation),
                "selection": float(row.selection),
                "interaction": float(row.interaction),
                "total": float(row.total),
            }
            for row in result.rows
        ],
        "inputs": "portfolio weights/returns from holdings + observed prices; "
        "benchmark weights/returns supplied by the caller",
        "formula": result.formula,
    }


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------


_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "trade_date", "transaction_date", "trade date"),
    "ticker": ("ticker", "symbol", "security"),
    "type": ("type", "transaction_type", "action", "side"),
    "quantity": ("quantity", "qty", "shares", "units"),
    "price": ("price", "trade_price", "unit_price", "price_per_share"),
    "currency": ("currency", "ccy", "trade_currency"),
    "commission": ("commission", "fees", "fee"),
    "fx_rate": ("fx_rate", "fx", "exchange_rate"),
    "external_id": ("external_id", "id", "transaction_id", "reference"),
    "notes": ("notes", "note", "description", "memo"),
}


def _canonical_columns(
    fieldnames: Sequence[str], mapping: dict[str, str] | None
) -> tuple[dict[str, str], list[str]]:
    normalized = {name.strip().lower(): name for name in fieldnames}
    resolved: dict[str, str] = {}
    if mapping:
        for canonical, actual in mapping.items():
            key = canonical.strip().lower()
            if key not in _ALIASES:
                continue
            if actual not in fieldnames:
                raise ValidationFailedError(f"Mapped column {actual!r} is not present in the CSV.")
            resolved[key] = actual
    for canonical, aliases in _ALIASES.items():
        if canonical in resolved:
            continue
        for alias in aliases:
            if alias in normalized:
                resolved[canonical] = normalized[alias]
                break
    return resolved, [name for name in ("date", "ticker", "type", "quantity", "price") if name not in resolved]


def parse_csv_transactions(
    content_str: str,
    *,
    mapping: dict[str, str] | None = None,
    default_currency: str = "USD",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse and validate a transaction CSV.

    Required columns: date, ticker, type, quantity, price.  Column names are
    case-insensitive and alias-aware; an explicit ``mapping`` (canonical -> header)
    overrides detection.  Dates must be ISO ``YYYY-MM-DD``; ambiguous formats are
    rejected rather than guessed.  Each record receives a stable SHA-256
    ``external_id`` when none is supplied so re-imports are idempotent.
    """
    reader = csv.DictReader(io.StringIO(content_str))
    if not reader.fieldnames:
        return [], [{"row": 0, "error": "CSV file is empty or headers are missing."}]
    try:
        columns, missing = _canonical_columns(reader.fieldnames, mapping)
    except ValidationFailedError as exc:
        return [], [{"row": 0, "error": exc.message}]
    if missing:
        return [], [{"row": 0, "error": f"Missing required columns: {', '.join(missing)}"}]

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row_index, row in enumerate(reader, start=2):
        try:
            raw_date = (row.get(columns["date"]) or "").strip()
            try:
                trade_date = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(f"date must be ISO YYYY-MM-DD (got {raw_date!r})") from exc
            ticker = (row.get(columns["ticker"]) or "").strip().upper()
            if not ticker:
                raise ValueError("ticker cannot be blank")
            transaction_type = (row.get(columns["type"]) or "").strip().upper()
            if transaction_type not in TRANSACTION_TYPES:
                raise ValueError(
                    f"type must be one of {', '.join(TRANSACTION_TYPES)} (got {transaction_type!r})"
                )
            try:
                quantity = Decimal((row.get(columns["quantity"]) or "").strip())
                price = Decimal((row.get(columns["price"]) or "").strip() or "0")
            except InvalidOperation as exc:
                raise ValueError("quantity and price must be decimal numbers") from exc
            if quantity <= ZERO:
                raise ValueError("quantity must be positive")
            if transaction_type != "SPLIT" and price < ZERO:
                raise ValueError("price cannot be negative")
            currency = (
                (row.get(columns.get("currency", "")) or default_currency).strip().upper()
            )
            commission_raw = (row.get(columns.get("commission", "")) or "0").strip()
            try:
                commission = Decimal(commission_raw or "0")
            except InvalidOperation as exc:
                raise ValueError("commission must be a decimal number") from exc
            if commission < ZERO:
                raise ValueError("commission cannot be negative")
            fx_raw = (row.get(columns.get("fx_rate", "")) or "").strip()
            fx_rate: Decimal | None = None
            if fx_raw:
                try:
                    fx_rate = Decimal(fx_raw)
                except InvalidOperation as exc:
                    raise ValueError("fx_rate must be a decimal number") from exc
                if fx_rate <= ZERO:
                    raise ValueError("fx_rate must be positive")
            notes = (row.get(columns.get("notes", "")) or "").strip() or None
            external_id = (row.get(columns.get("external_id", "")) or "").strip()
            fingerprint = "|".join(
                [
                    trade_date.isoformat(),
                    ticker,
                    transaction_type,
                    str(quantity),
                    str(price),
                    currency,
                    str(commission),
                    fx_raw,
                    notes or "",
                ]
            )
            external_id = external_id or "sha256:" + hashlib.sha256(fingerprint.encode()).hexdigest()
            if len(external_id) > 128:
                raise ValueError("external_id must be at most 128 characters")
            if external_id in seen_ids:
                errors.append(
                    {"row": row_index, "error": f"duplicate external_id {external_id!r}", "data": row}
                )
                continue
            seen_ids.add(external_id)
            records.append(
                {
                    "trade_date": trade_date,
                    "ticker": ticker,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "price": price,
                    "currency": currency,
                    "commission": commission,
                    "fx_rate": fx_rate,
                    "external_id": external_id,
                    "notes": notes,
                    "row": row_index,
                }
            )
        except (ValueError, KeyError) as exc:
            errors.append({"row": row_index, "error": str(exc), "data": row})
    return records, errors
