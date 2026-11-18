"""Company research endpoints: overview, price series, statements, ratios, peers, filings."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from analystforge.api.deps import SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.research import Filing
from analystforge.api.services.company import (
    get_company_overview,
    get_company_ratios,
    get_instrument_by_symbol,
    get_peers,
    get_price_history,
    load_financial_statements,
    search_instruments,
)

router = APIRouter(prefix="/companies", tags=["companies"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CompanyOverviewResponse(BaseModel):
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
    latest_price: float | None
    latest_price_date: str | None
    change_pct: float | None
    high_52w: float | None
    low_52w: float | None
    market_cap: float | None
    volume: int | None


class PriceBarItem(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


class RatioItem(BaseModel):
    key: str
    label: str
    category: str
    value: float | None
    unit: str
    formula: str
    inputs: dict[str, Any]
    note: str | None = None


class PeerItem(BaseModel):
    id: str
    ticker: str
    name: str
    exchange: str
    sector: str | None
    industry: str | None
    currency: str
    price: float | None


class FilingItem(BaseModel):
    id: uuid.UUID
    form: str
    filed_date: str
    period_of_report: str | None
    primary_document: str
    document_url: str


class SearchItem(BaseModel):
    id: str
    ticker: str
    name: str
    exchange: str
    currency: str
    sector: str | None
    industry: str | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/search", summary="Search active instruments by symbol or name")
async def search(
    query: Annotated[str, Query(min_length=1, max_length=50)],
    session: SessionDep,
) -> list[SearchItem]:
    results = await search_instruments(session, query)
    return [SearchItem(**r) for r in results]


@router.get("/{ticker}", summary="Company profile, current quote and key statistics")
async def get_company(
    ticker: str,
    session: SessionDep,
) -> CompanyOverviewResponse:
    instrument = await get_instrument_by_symbol(session, ticker)
    if not instrument:
        raise NotFoundError(f"Company with symbol '{ticker}' not found.")

    overview = await get_company_overview(session, instrument)
    return CompanyOverviewResponse(
        id=overview.id,
        ticker=overview.ticker,
        name=overview.name,
        exchange_code=overview.exchange_code,
        exchange_name=overview.exchange_name,
        currency=overview.currency,
        asset_type=overview.asset_type,
        cik=overview.cik,
        sector=overview.sector,
        industry=overview.industry,
        description=overview.description,
        latest_price=float(overview.latest_price) if overview.latest_price is not None else None,
        latest_price_date=overview.latest_price_date.isoformat()
        if overview.latest_price_date
        else None,
        change_pct=overview.change_pct,
        high_52w=float(overview.high_52w) if overview.high_52w is not None else None,
        low_52w=float(overview.low_52w) if overview.low_52w is not None else None,
        market_cap=float(overview.market_cap) if overview.market_cap is not None else None,
        volume=overview.volume,
    )


@router.get("/{ticker}/prices", summary="Historical OHLCV candlestick price bars")
async def get_prices(
    ticker: str,
    session: SessionDep,
    interval: Annotated[str, Query(pattern="^(1d|1wk|1mo)$")] = "1d",
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[PriceBarItem]:
    instrument = await get_instrument_by_symbol(session, ticker)
    if not instrument:
        raise NotFoundError(f"Company with symbol '{ticker}' not found.")

    bars = await get_price_history(
        session, instrument.id, interval=interval, start=from_date, end=to_date, limit=limit
    )
    return [PriceBarItem(**b) for b in bars]


@router.get("/{ticker}/statements", summary="Normalized annual financial statements")
async def get_statements(
    ticker: str,
    session: SessionDep,
) -> dict[str, Any]:
    instrument = await get_instrument_by_symbol(session, ticker)
    if not instrument:
        raise NotFoundError(f"Company with symbol '{ticker}' not found.")

    stmts_list = await load_financial_statements(session, instrument.id)
    if not stmts_list:
        return {"income": [], "balance": [], "cashflow": []}

    income_rows: list[dict[str, Any]] = []
    balance_rows: list[dict[str, Any]] = []
    cashflow_rows: list[dict[str, Any]] = []

    for s in stmts_list:
        inc = {
            "fiscal_year": s.income.fiscal_year,
            "period": s.income.fiscal_period.value,
            "values": {k.value: float(v) for k, v in s.income.values.items()},
        }
        income_rows.append(inc)

        bal = {
            "fiscal_year": s.balance.fiscal_year,
            "period": s.balance.fiscal_period.value,
            "values": {k.value: float(v) for k, v in s.balance.values.items()},
        }
        balance_rows.append(bal)

        if s.cashflow:
            cf = {
                "fiscal_year": s.cashflow.fiscal_year,
                "period": s.cashflow.fiscal_period.value,
                "values": {k.value: float(v) for k, v in s.cashflow.values.items()},
            }
            cashflow_rows.append(cf)

    return {
        "ticker": instrument.ticker,
        "currency": instrument.currency,
        "income": income_rows,
        "balance": balance_rows,
        "cashflow": cashflow_rows,
    }


@router.get("/{ticker}/ratios", summary="Comprehensive ratio suite with formulas and input values")
async def get_ratios(
    ticker: str,
    session: SessionDep,
) -> list[RatioItem]:
    instrument = await get_instrument_by_symbol(session, ticker)
    if not instrument:
        raise NotFoundError(f"Company with symbol '{ticker}' not found.")

    ratios = await get_company_ratios(session, instrument)
    return [RatioItem(**r) for r in ratios]


@router.get("/{ticker}/peers", summary="Sector peer group and comparative valuation metrics")
async def get_company_peers(
    ticker: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[PeerItem]:
    instrument = await get_instrument_by_symbol(session, ticker)
    if not instrument:
        raise NotFoundError(f"Company with symbol '{ticker}' not found.")

    peers = await get_peers(session, instrument, limit=limit)
    return [PeerItem(**p) for p in peers]


@router.get("/{ticker}/filings", summary="SEC Edgar filing history (10-K, 10-Q, 8-K)")
async def get_filings(
    ticker: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[FilingItem]:
    instrument = await get_instrument_by_symbol(session, ticker)
    if not instrument:
        raise NotFoundError(f"Company with symbol '{ticker}' not found.")

    stmt = (
        select(Filing)
        .where(Filing.instrument_id == instrument.id)
        .order_by(desc(Filing.filed_date))
        .limit(limit)
    )
    res = await session.execute(stmt)
    filings = res.scalars().all()

    return [
        FilingItem(
            id=f.id,
            form=f.form,
            filed_date=f.filed_date.isoformat(),
            period_of_report=f.period_of_report.isoformat() if f.period_of_report else None,
            primary_document=f.primary_document,
            document_url=f.document_url,
        )
        for f in filings
    ]
