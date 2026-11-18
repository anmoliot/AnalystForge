"""Company research service: instruments, price history, normalized statements and ratios."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.market import Exchange, Instrument, InstrumentProviderSymbol, PriceBar
from analystforge.api.models.research import FundamentalFact
from analystforge.quant.money import to_decimal
from analystforge.quant.ratios import MarketData, compute_ratios
from analystforge.quant.statements import (
    FinancialFact,
    FinancialStatements,
    FiscalPeriod,
    NormalizedStatement,
    StatementType,
    normalize_statement,
)


@dataclass(frozen=True, slots=True)
class CompanyOverview:
    id: uuid.UUID
    ticker: str
    name: str
    exchange_code: str
    exchange_name: str
    currency: str
    asset_type: str
    cik: str | None
    sector: str | None
    industry: str | None
    description: str | None
    latest_price: Decimal | None
    latest_price_date: datetime | None
    change_pct: float | None
    high_52w: Decimal | None
    low_52w: Decimal | None
    market_cap: Decimal | None
    volume: int | None


async def get_instrument_by_symbol(
    session: AsyncSession, symbol_or_ticker: str
) -> Instrument | None:
    """Find instrument by ticker or provider symbol (case-insensitive)."""
    norm = symbol_or_ticker.strip().upper()

    # Direct match on ticker
    stmt = select(Instrument).where(func.upper(Instrument.ticker) == norm)
    result = await session.execute(stmt)
    instrument = result.scalar_one_or_none()
    if instrument:
        return instrument

    # Match on provider symbol
    sym_stmt = (
        select(Instrument)
        .join(InstrumentProviderSymbol, InstrumentProviderSymbol.instrument_id == Instrument.id)
        .where(func.upper(InstrumentProviderSymbol.symbol) == norm)
    )
    result = await session.execute(sym_stmt)
    return result.scalar_one_or_none()


async def get_company_overview(session: AsyncSession, instrument: Instrument) -> CompanyOverview:
    # Exchange details
    exchange = await session.get(Exchange, instrument.exchange_code)
    exchange_name = exchange.name if exchange else instrument.exchange_code

    # Latest price bars
    bars_stmt = (
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id)
        .order_by(desc(PriceBar.ts))
        .limit(2)
    )
    bars_res = await session.execute(bars_stmt)
    recent_bars = bars_res.scalars().all()

    latest_price: Decimal | None = None
    latest_price_date: datetime | None = None
    change_pct: float | None = None

    if recent_bars:
        latest = recent_bars[0]
        latest_price = latest.close
        latest_price_date = latest.ts
        if len(recent_bars) > 1 and recent_bars[1].close > 0:
            prev = recent_bars[1].close
            change_pct = float((latest.close - prev) / prev * 100)

    # 52-week high / low
    agg_stmt = select(
        func.max(PriceBar.high),
        func.min(PriceBar.low),
        func.sum(PriceBar.volume),
    ).where(PriceBar.instrument_id == instrument.id)
    agg_res = await session.execute(agg_stmt)
    agg_row = agg_res.fetchone()
    high_52w = agg_row[0] if agg_row else None
    low_52w = agg_row[1] if agg_row else None
    volume = int(recent_bars[0].volume) if recent_bars and recent_bars[0].volume else None

    # Derive market cap from shares outstanding fact or instrument metadata
    market_cap: Decimal | None = None
    shares_fact_stmt = (
        select(FundamentalFact.value)
        .where(
            FundamentalFact.instrument_id == instrument.id,
            FundamentalFact.concept.ilike("%EntityCommonStockSharesOutstanding%"),
        )
        .order_by(desc(FundamentalFact.filed))
        .limit(1)
    )
    shares_res = await session.execute(shares_fact_stmt)
    shares_val = shares_res.scalar_one_or_none()
    if shares_val and latest_price:
        market_cap = latest_price * shares_val
    elif instrument.extra.get("market_cap"):
        market_cap = to_decimal(instrument.extra["market_cap"])

    return CompanyOverview(
        id=instrument.id,
        ticker=instrument.ticker,
        name=instrument.name,
        exchange_code=instrument.exchange_code,
        exchange_name=exchange_name,
        currency=instrument.currency,
        asset_type=instrument.asset_type,
        cik=instrument.cik,
        sector=instrument.sector,
        industry=instrument.industry,
        description=instrument.description,
        latest_price=latest_price,
        latest_price_date=latest_price_date,
        change_pct=change_pct,
        high_52w=high_52w,
        low_52w=low_52w,
        market_cap=market_cap,
        volume=volume,
    )


async def get_price_history(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    interval: str = "1d",
    start: date | None = None,
    end: date | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    query = select(PriceBar).where(
        PriceBar.instrument_id == instrument_id, PriceBar.interval == interval
    )
    if start:
        query = query.where(PriceBar.ts >= datetime.combine(start, datetime.min.time(), tzinfo=UTC))
    if end:
        query = query.where(PriceBar.ts <= datetime.combine(end, datetime.max.time(), tzinfo=UTC))

    query = query.order_by(PriceBar.ts).limit(limit)
    res = await session.execute(query)
    bars = res.scalars().all()

    return [
        {
            "time": bar.ts.strftime("%Y-%m-%d"),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "adjusted_close": float(bar.adjusted_close)
            if bar.adjusted_close is not None
            else float(bar.close),
            "volume": bar.volume or 0,
        }
        for bar in bars
    ]


async def load_financial_statements(
    session: AsyncSession, instrument_id: uuid.UUID
) -> list[FinancialStatements]:
    """Load and normalize financial statements across available fiscal periods."""
    facts_stmt = (
        select(FundamentalFact)
        .where(FundamentalFact.instrument_id == instrument_id)
        .order_by(desc(FundamentalFact.filed))
    )
    res = await session.execute(facts_stmt)
    db_facts = res.scalars().all()
    if not db_facts:
        return []

    # Group facts into FinancialFact dataclasses
    facts: list[FinancialFact] = [
        FinancialFact(
            concept=f.concept,
            value=f.value,
            unit=f.unit,
            period_end=f.period_end,
            period_start=f.period_start
            if f.period_start and f.period_start != f.period_end
            else None,
            fiscal_year=f.fiscal_year or f.period_end.year,
            fiscal_period=f.fiscal_period or "FY",
            form=f.form,
            filed=f.filed,
            accession=f.accession,
        )
        for f in db_facts
    ]

    # Discover fiscal years
    years = sorted({f.fiscal_year for f in facts if f.fiscal_year is not None}, reverse=True)
    statements_list: list[FinancialStatements] = []

    for yr in years:
        try:
            inc = normalize_statement(facts, StatementType.INCOME, yr, FiscalPeriod.FY)
            bal = normalize_statement(facts, StatementType.BALANCE, yr, FiscalPeriod.FY)
            cf: NormalizedStatement | None = None
            try:
                cf = normalize_statement(facts, StatementType.CASH_FLOW, yr, FiscalPeriod.FY)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "operation unavailable (%s)", type(exc).__name__
                )
                cf = None
            statements_list.append(FinancialStatements(income=inc, balance=bal, cashflow=cf))
        except Exception as exc:
            logging.getLogger(__name__).warning("operation unavailable (%s)", type(exc).__name__)
            continue

    return statements_list


async def get_company_ratios(session: AsyncSession, instrument: Instrument) -> list[dict[str, Any]]:
    """Compute and format all ratios for the instrument."""
    statements = await load_financial_statements(session, instrument.id)
    if not statements:
        return []

    latest_stmt = statements[0]
    prior_stmt = statements[1] if len(statements) > 1 else None

    # Get latest market price for valuation ratios
    bar_stmt = (
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id)
        .order_by(desc(PriceBar.ts))
        .limit(1)
    )
    bar_res = await session.execute(bar_stmt)
    latest_bar = bar_res.scalar_one_or_none()

    market_data: MarketData | None = None
    if latest_bar:
        market_data = MarketData(
            price=latest_bar.close,
            as_of=latest_bar.ts.date(),
        )

    ratios_dict = compute_ratios(
        statements=latest_stmt,
        market=market_data,
        prior=prior_stmt,
    )

    out: list[dict[str, Any]] = []
    for _key, item in ratios_dict.items():
        val = item.value
        numeric_val: float | None = None
        if val is not None:
            numeric_val = float(val)

        inputs_formatted = {
            k: float(v)
            if isinstance(v, (Decimal, int, float)) and v is not None
            else str(v)
            if v is not None
            else None
            for k, v in item.inputs.items()
        }

        out.append(
            {
                "key": item.key,
                "label": item.label,
                "category": item.category.value,
                "value": numeric_val,
                "unit": item.unit.value,
                "formula": item.formula,
                "inputs": inputs_formatted,
                "note": item.note,
            }
        )

    return out


async def get_peers(
    session: AsyncSession, instrument: Instrument, limit: int = 10
) -> list[dict[str, Any]]:
    """Find sector peers and compare key valuation metrics."""
    if not instrument.sector:
        return []

    peers_stmt = (
        select(Instrument)
        .where(
            Instrument.sector == instrument.sector,
            Instrument.id != instrument.id,
            Instrument.is_active.is_(True),
        )
        .limit(limit)
    )
    res = await session.execute(peers_stmt)
    peers = res.scalars().all()

    peer_data: list[dict[str, Any]] = []
    for peer in peers:
        # Get latest price
        pbar_stmt = (
            select(PriceBar.close, PriceBar.ts)
            .where(PriceBar.instrument_id == peer.id)
            .order_by(desc(PriceBar.ts))
            .limit(1)
        )
        p_res = await session.execute(pbar_stmt)
        p_row = p_res.fetchone()
        price = float(p_row[0]) if p_row else None

        peer_data.append(
            {
                "id": str(peer.id),
                "ticker": peer.ticker,
                "name": peer.name,
                "exchange": peer.exchange_code,
                "sector": peer.sector,
                "industry": peer.industry,
                "currency": peer.currency,
                "price": price,
            }
        )

    return peer_data


async def search_instruments(
    session: AsyncSession, query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Search active instruments by ticker or name."""
    pattern = f"%{query.strip().upper()}%"
    stmt = (
        select(Instrument)
        .where(
            Instrument.is_active.is_(True),
            or_(
                func.upper(Instrument.ticker).like(pattern),
                func.upper(Instrument.name).like(pattern),
            ),
        )
        .order_by(Instrument.ticker)
        .limit(limit)
    )
    res = await session.execute(stmt)
    items = res.scalars().all()
    return [
        {
            "id": str(item.id),
            "ticker": item.ticker,
            "name": item.name,
            "exchange": item.exchange_code,
            "currency": item.currency,
            "sector": item.sector,
            "industry": item.industry,
        }
        for item in items
    ]
