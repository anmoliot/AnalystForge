"""Portfolio management, holdings, transaction import, risk analytics, and optimization."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import DataUnavailableError, NotFoundError, ValidationFailedError
from analystforge.api.models.market import Instrument, PriceBar
from analystforge.api.models.portfolio import Portfolio, PortfolioTransaction
from analystforge.api.services.portfolio import (
    compute_black_litterman_portfolio,
    compute_fama_french_exposure,
    compute_holdings_fifo,
    compute_portfolio_analytics,
    compute_rolling_statistics,
    compute_sector_attribution,
    enrich_holdings_with_prices,
    execute_stress_tests,
    latest_prices,
    load_price_histories,
    optimize_weights,
    parse_transactions_file,
    preview_transactions_file,
)
from analystforge.quant.rebalance import generate_rebalance_trades

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreatePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    base_currency: str = Field(default="USD", max_length=8)
    benchmark_ticker: str = Field(default="SPY", max_length=32)
    cost_basis_method: str = Field(default="FIFO", max_length=16)


class TransactionRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    transaction_type: str = Field(pattern="^(BUY|SELL|DIVIDEND|SPLIT|FEE)$")
    trade_date: date
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    currency: str = "USD"
    commission: float = 0.0
    notes: str | None = None


class HoldingResponse(BaseModel):
    ticker: str
    shares: float
    cost_basis: float
    total_cost: float
    current_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    weight: float | None


class PortfolioDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    base_currency: str
    benchmark_ticker: str
    cost_basis_method: str
    total_value: float
    total_cost: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    holdings: list[HoldingResponse]


class OptimizePortfolioRequest(BaseModel):
    objective: str = "max_sharpe"
    risk_free_rate: float = 0.04
    min_weight: float = 0.0
    max_weight: float = 1.0
    initial_weights: list[float] | None = None
    turnover_cap: float | None = None
    asset_sectors: list[str] | None = None
    sector_caps: dict[str, float] | None = None


class RebalanceRequest(BaseModel):
    target_weights: dict[str, float]
    cash: float = 0.0
    commission_bps: float = 10.0
    allow_fractional: bool = True
    min_trade_size: float = 1.0


class BlackLittermanRequest(BaseModel):
    market_weights: dict[str, float] | None = None
    views: list[dict[str, Any]] | None = None
    risk_aversion: float = 2.5
    tau: float = 0.05
    risk_free_rate: float = 0.04


class AttributionRequest(BaseModel):
    benchmark_groups: list[dict[str, Any]]
    start: date | None = None
    end: date | None = None
    method: str = "bf"


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201, summary="Create a new portfolio")
async def create_portfolio(
    body: CreatePortfolioRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = Portfolio(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        base_currency=body.base_currency.upper(),
        benchmark_ticker=body.benchmark_ticker.upper(),
        cost_basis_method=body.cost_basis_method.upper(),
    )
    session.add(port)
    await session.commit()
    return {"id": str(port.id), "name": port.name, "created_at": port.created_at.isoformat()}


@router.get("", summary="List tenant portfolios")
async def list_portfolios(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    stmt = (
        select(Portfolio)
        .where(Portfolio.tenant_id == current_user.tenant_id)
        .order_by(desc(Portfolio.updated_at))
    )
    res = await session.execute(stmt)
    ports = res.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "base_currency": p.base_currency,
            "benchmark_ticker": p.benchmark_ticker,
            "created_at": p.created_at.isoformat(),
        }
        for p in ports
    ]


@router.get("/{portfolio_id}", summary="Get portfolio with holdings and real-time market value")
async def get_portfolio(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> PortfolioDetailResponse:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = (
        select(PortfolioTransaction)
        .where(PortfolioTransaction.portfolio_id == port.id)
        .order_by(PortfolioTransaction.trade_date)
    )
    tx_res = await session.execute(tx_stmt)
    txs = tx_res.scalars().all()

    raw_holdings = compute_holdings_fifo(txs)
    enriched = await enrich_holdings_with_prices(session, raw_holdings)

    tot_val = sum((h.market_value or Decimal(0)) for h in enriched)
    tot_cost = sum(h.total_cost for h in enriched)
    tot_pnl = tot_val - tot_cost
    tot_pnl_pct = float(tot_pnl / tot_cost) if tot_cost > 0 else 0.0

    return PortfolioDetailResponse(
        id=port.id,
        name=port.name,
        description=port.description,
        base_currency=port.base_currency,
        benchmark_ticker=port.benchmark_ticker,
        cost_basis_method=port.cost_basis_method,
        total_value=float(tot_val),
        total_cost=float(tot_cost),
        total_unrealized_pnl=float(tot_pnl),
        total_unrealized_pnl_pct=tot_pnl_pct,
        holdings=[
            HoldingResponse(
                ticker=h.ticker,
                shares=float(h.shares),
                cost_basis=float(h.cost_basis),
                total_cost=float(h.total_cost),
                current_price=float(h.current_price) if h.current_price is not None else None,
                market_value=float(h.market_value) if h.market_value is not None else None,
                unrealized_pnl=float(h.unrealized_pnl) if h.unrealized_pnl is not None else None,
                unrealized_pnl_pct=h.unrealized_pnl_pct,
                weight=h.weight,
            )
            for h in enriched
        ],
    )


@router.post("/{portfolio_id}/transactions", status_code=201, summary="Add a single transaction")
async def add_transaction(
    portfolio_id: uuid.UUID,
    body: TransactionRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx = PortfolioTransaction(
        portfolio_id=port.id,
        ticker=body.ticker.upper(),
        transaction_type=body.transaction_type.upper(),
        trade_date=body.trade_date,
        quantity=Decimal(str(body.quantity)),
        price=Decimal(str(body.price)),
        currency=body.currency.upper(),
        commission=Decimal(str(body.commission)),
        notes=body.notes,
    )
    session.add(tx)
    await session.commit()
    return {"id": str(tx.id), "ticker": tx.ticker, "trade_date": tx.trade_date.isoformat()}


@router.get("/{portfolio_id}/transactions", summary="List transactions for portfolio")
async def list_transactions(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    stmt = (
        select(PortfolioTransaction)
        .where(PortfolioTransaction.portfolio_id == port.id)
        .order_by(desc(PortfolioTransaction.trade_date))
    )
    res = await session.execute(stmt)
    txs = res.scalars().all()
    return [
        {
            "id": str(t.id),
            "ticker": t.ticker,
            "type": t.transaction_type,
            "trade_date": t.trade_date.isoformat(),
            "quantity": float(t.quantity),
            "price": float(t.price),
            "currency": t.currency,
            "commission": float(t.commission),
            "notes": t.notes,
        }
        for t in txs
    ]


@router.post(
    "/{portfolio_id}/import/preview",
    summary="Preview transactions file with column mapping suggestions",
)
async def preview_transactions(
    portfolio_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    session: SessionDep = None,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    content = await file.read()
    return preview_transactions_file(content, file.filename or "transactions.csv")


@router.post(
    "/{portfolio_id}/import",
    summary="Import transactions from CSV or Excel with column mapping & validation report",
)
async def import_transactions(
    portfolio_id: uuid.UUID,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    current_user: CurrentUser = None,
    session: SessionDep = None,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    content = await file.read()
    mapping_dict: dict[str, str] | None = None
    if mapping:
        try:
            parsed = json.loads(mapping)
            if isinstance(parsed, dict):
                mapping_dict = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            mapping_dict = None

    valid_records, errors = parse_transactions_file(
        content,
        file.filename or "transactions.csv",
        mapping=mapping_dict,
        default_currency=port.base_currency,
    )
    if not valid_records and errors:
        raise ValidationFailedError(f"Import failed: {errors[0]['error']}")

    for rec in valid_records:
        tx = PortfolioTransaction(
            portfolio_id=port.id,
            ticker=rec["ticker"],
            transaction_type=rec["transaction_type"],
            trade_date=rec["trade_date"],
            quantity=rec["quantity"],
            price=rec["price"],
            currency=rec["currency"],
            commission=rec["commission"],
            notes=rec["notes"],
        )
        session.add(tx)

    await session.commit()
    return {
        "status": "success",
        "imported_count": len(valid_records),
        "error_count": len(errors),
        "errors": errors[:50],
        "validation_report": {
            "filename": file.filename,
            "total_rows": len(valid_records) + len(errors),
            "valid_rows": len(valid_records),
            "error_rows": len(errors),
            "errors": errors,
        },
    }


@router.post("/{portfolio_id}/import/download-report", summary="Download validation report as CSV")
async def download_import_report(
    portfolio_id: uuid.UUID,
    report_data: dict[str, Any],
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    errors = report_data.get("errors", [])
    csv_lines = ["row,status,ticker,error,details"]
    for err in errors:
        row_num = err.get("row", "")
        msg = str(err.get("error", "")).replace('"', '""')
        raw_data = str(err.get("data", {})).replace('"', '""')
        csv_lines.append(f'{row_num},ERROR,"","{msg}","{raw_data}"')

    content = "\n".join(csv_lines)
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="validation_report_{portfolio_id}.csv"'
        },
    )


@router.get(
    "/{portfolio_id}/risk",
    summary="Quantitative risk analytics suite (VaR, CVaR, Sharpe, Drawdown)",
)
async def get_portfolio_risk(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    # Retrieve holdings and price series
    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)

    if not holdings:
        return {
            "volatility": 0.0,
            "sharpe": None,
            "sortino": None,
            "max_drawdown": 0.0,
            "var_95_hist": 0.0,
            "var_95_param": 0.0,
            "cvar_95": 0.0,
        }

    # Fetch daily price history for holdings
    tickers = [h.ticker for h in holdings]
    inst_stmt = select(Instrument).where(Instrument.ticker.in_(tickers))
    instruments = {
        inst.ticker: inst.id for inst in (await session.execute(inst_stmt)).scalars().all()
    }

    daily_prices: dict[str, pd.Series] = {}
    for ticker, inst_id in instruments.items():
        bar_stmt = (
            select(PriceBar.ts, PriceBar.close)
            .where(PriceBar.instrument_id == inst_id, PriceBar.interval == "1d")
            .order_by(PriceBar.ts)
        )
        bar_rows = (await session.execute(bar_stmt)).fetchall()
        if len(bar_rows) >= 5:
            dates = [r[0] for r in bar_rows]
            prices = [float(r[1]) for r in bar_rows]
            daily_prices[ticker] = pd.Series(prices, index=pd.to_datetime(dates))

    if not daily_prices or len(pd.DataFrame(daily_prices).dropna()) < 5:
        missing_tickers = [t for t in tickers if t not in daily_prices or len(daily_prices[t]) < 5]
        raise DataUnavailableError(
            "Insufficient price history for portfolio holdings; fabricated numbers are disallowed",
            details={
                "tickers": tickers,
                "missing_tickers": missing_tickers,
                "available_bars": {t: len(s) for t, s in daily_prices.items()},
                "required_bars": 5,
            },
        )

    df_prices = pd.DataFrame(daily_prices).dropna()

    returns_df = df_prices.pct_change().dropna()
    weights = [float(h.total_cost) for h in holdings if h.ticker in returns_df.columns]
    tot_w = sum(weights) or 1.0
    w_vec = np.array([w / tot_w for w in weights])

    port_returns = returns_df.dot(w_vec)
    return compute_portfolio_analytics(port_returns)


@router.post(
    "/{portfolio_id}/optimize", summary="Mean-variance, Max Sharpe, and Risk Parity optimizer"
)
async def optimize_portfolio_endpoint(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    objective: Annotated[
        str, Query(pattern="^(max_sharpe|min_variance|risk_parity)$")
    ] = "max_sharpe",
    body: OptimizePortfolioRequest | None = None,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)
    tickers = [h.ticker for h in holdings]

    if len(tickers) < 2:
        raise ValidationFailedError(
            "Portfolio must contain at least 2 distinct asset holdings for portfolio optimization; fabricated numbers are disallowed."
        )

    # Fetch price history to compute covariance matrix
    inst_stmt = select(Instrument).where(Instrument.ticker.in_(tickers))
    inst_map = {inst.ticker: inst.id for inst in (await session.execute(inst_stmt)).scalars().all()}

    daily_dict: dict[str, list[float]] = {}
    for ticker in tickers:
        inst_id = inst_map.get(ticker)
        if inst_id:
            bar_stmt = (
                select(PriceBar.close)
                .where(PriceBar.instrument_id == inst_id)
                .order_by(PriceBar.ts)
            )
            rows = (await session.execute(bar_stmt)).scalars().all()
            if rows:
                daily_dict[ticker] = [float(r) for r in rows]

    # Align series
    min_len = min((len(v) for v in daily_dict.values()), default=0)
    if min_len < 10 or len(daily_dict) < len(tickers):
        missing_or_sparse = [t for t in tickers if len(daily_dict.get(t, [])) < 10]
        raise DataUnavailableError(
            "Insufficient aligned price history for portfolio optimization; fabricated numbers are disallowed",
            details={
                "tickers": tickers,
                "sparse_tickers": missing_or_sparse,
                "available_bars": {t: len(v) for t, v in daily_dict.items()},
                "required_bars": 10,
            },
        )

    clean_dict = {t: v[-min_len:] for t, v in daily_dict.items()}
    prices_df = pd.DataFrame(clean_dict)
    ret_df = prices_df.pct_change().dropna()

    req_obj = body.objective if body else objective
    rf = body.risk_free_rate if body else 0.04
    min_w = body.min_weight if body else 0.0
    max_w = body.max_weight if body else 1.0
    turnover_cap = body.turnover_cap if body else None
    initial_weights = body.initial_weights if body else None
    asset_sectors = body.asset_sectors if body else None
    sector_caps = body.sector_caps if body else None

    return optimize_weights(
        ret_df,
        objective=req_obj,
        risk_free_rate=rf,
        min_weight=min_w,
        max_weight=max_w,
        initial_weights=initial_weights,
        turnover_cap=turnover_cap,
        asset_sectors=asset_sectors,
        sector_caps=sector_caps,
    )


@router.post(
    "/{portfolio_id}/rebalance", summary="Generate rebalance trade orders for target weights"
)
async def rebalance_portfolio_endpoint(
    portfolio_id: uuid.UUID,
    body: RebalanceRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)

    all_tickers = sorted(set(list(body.target_weights.keys()) + [h.ticker for h in holdings]))
    prices_map = await latest_prices(session, all_tickers)
    missing = [t for t in all_tickers if t not in prices_map]
    if missing:
        raise DataUnavailableError(f"Missing current price for tickers: {', '.join(missing)}")

    current_shares = {h.ticker: h.shares for h in holdings}
    for t in all_tickers:
        if t not in current_shares:
            current_shares[t] = Decimal("0")

    prices_only = {t: info[0] for t, info in prices_map.items()}

    plan = generate_rebalance_trades(
        current_shares=current_shares,
        prices=prices_only,
        target_weights=body.target_weights,
        cash=Decimal(str(body.cash)),
        commission_bps=Decimal(str(body.commission_bps)),
        allow_fractional=body.allow_fractional,
        min_trade_size=Decimal(str(body.min_trade_size)),
    )

    return {
        "portfolio_id": str(port.id),
        "portfolio_value": float(plan.portfolio_value),
        "starting_cash": float(plan.starting_cash),
        "ending_cash": float(plan.ending_cash),
        "turnover": float(plan.turnover),
        "total_traded_value": float(plan.total_traded_value),
        "total_estimated_commissions": float(plan.total_estimated_commissions),
        "orders": [
            {
                "ticker": o.ticker,
                "action": str(o.action),
                "current_shares": float(o.current_shares),
                "target_shares": float(o.target_shares),
                "delta_shares": float(o.delta_shares),
                "price": float(o.price),
                "current_value": float(o.current_value),
                "target_value": float(o.target_value),
                "trade_value": float(o.trade_value),
                "current_weight": float(o.current_weight),
                "target_weight": float(o.target_weight),
                "weight_delta": float(o.weight_delta),
                "estimated_commission": float(o.estimated_commission),
            }
            for o in plan.orders
        ],
    }


@router.get("/{portfolio_id}/factors", summary="Fama-French factor exposure regression")
async def get_fama_french_exposure(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)
    tickers = [h.ticker for h in holdings]
    bench_ticker = port.benchmark_ticker or "SPY"
    all_needed = list({*tickers, bench_ticker})

    inst_stmt = select(Instrument).where(Instrument.ticker.in_(all_needed))
    instruments = {
        inst.ticker: inst.id for inst in (await session.execute(inst_stmt)).scalars().all()
    }

    daily_prices: dict[str, pd.Series] = {}
    for ticker, inst_id in instruments.items():
        bar_stmt = (
            select(PriceBar.ts, PriceBar.close)
            .where(PriceBar.instrument_id == inst_id, PriceBar.interval == "1d")
            .order_by(PriceBar.ts)
        )
        bar_rows = (await session.execute(bar_stmt)).fetchall()
        if len(bar_rows) >= 5:
            dates = [r[0] for r in bar_rows]
            prices = [float(r[1]) for r in bar_rows]
            daily_prices[ticker] = pd.Series(prices, index=pd.to_datetime(dates))

    if not daily_prices or any(t not in daily_prices for t in tickers):
        raise DataUnavailableError(
            "Insufficient historical price bars to compute factor regression."
        )

    holding_prices = {t: daily_prices[t] for t in tickers}
    df_prices = pd.DataFrame(holding_prices).dropna()
    ret_df = df_prices.pct_change().dropna()
    weights = [float(h.total_cost) for h in holdings if h.ticker in ret_df.columns]
    tot_w = sum(weights) or 1.0
    w_vec = np.array([w / tot_w for w in weights])
    port_returns = ret_df.dot(w_vec)

    bench_series = daily_prices.get(bench_ticker)
    if bench_series is not None:
        bench_returns = bench_series.pct_change().dropna().reindex(port_returns.index).fillna(0.0)
    else:
        bench_returns = port_returns.copy()

    return compute_fama_french_exposure(port_returns, bench_returns)


@router.get("/{portfolio_id}/rolling", summary="Rolling risk and performance metrics")
async def get_rolling_metrics(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    window: Annotated[int, Query(ge=5, le=500)] = 20,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)
    tickers = [h.ticker for h in holdings]
    bench_ticker = port.benchmark_ticker or "SPY"
    all_needed = list({*tickers, bench_ticker})

    inst_stmt = select(Instrument).where(Instrument.ticker.in_(all_needed))
    instruments = {
        inst.ticker: inst.id for inst in (await session.execute(inst_stmt)).scalars().all()
    }

    daily_prices: dict[str, pd.Series] = {}
    for ticker, inst_id in instruments.items():
        bar_stmt = (
            select(PriceBar.ts, PriceBar.close)
            .where(PriceBar.instrument_id == inst_id, PriceBar.interval == "1d")
            .order_by(PriceBar.ts)
        )
        bar_rows = (await session.execute(bar_stmt)).fetchall()
        if len(bar_rows) >= 5:
            dates = [r[0] for r in bar_rows]
            prices = [float(r[1]) for r in bar_rows]
            daily_prices[ticker] = pd.Series(prices, index=pd.to_datetime(dates))

    if not daily_prices or any(t not in daily_prices for t in tickers):
        raise DataUnavailableError(
            "Insufficient historical price bars to compute rolling statistics."
        )

    holding_prices = {t: daily_prices[t] for t in tickers}
    df_prices = pd.DataFrame(holding_prices).dropna()
    ret_df = df_prices.pct_change().dropna()
    weights = [float(h.total_cost) for h in holdings if h.ticker in ret_df.columns]
    tot_w = sum(weights) or 1.0
    w_vec = np.array([w / tot_w for w in weights])
    port_returns = ret_df.dot(w_vec)

    bench_series = daily_prices.get(bench_ticker)
    if bench_series is not None:
        bench_returns = bench_series.pct_change().dropna().reindex(port_returns.index).fillna(0.0)
    else:
        bench_returns = port_returns.copy()

    return compute_rolling_statistics(port_returns, bench_returns, window=window)


@router.post(
    "/{portfolio_id}/black-litterman",
    summary="Black-Litterman expected returns and optimal allocation",
)
async def black_litterman_endpoint(
    portfolio_id: uuid.UUID,
    body: BlackLittermanRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)
    tickers = [h.ticker for h in holdings]

    if len(tickers) < 2:
        raise ValidationFailedError(
            "Black-Litterman model requires at least 2 distinct asset holdings."
        )

    inst_stmt = select(Instrument).where(Instrument.ticker.in_(tickers))
    inst_map = {inst.ticker: inst.id for inst in (await session.execute(inst_stmt)).scalars().all()}

    daily_dict: dict[str, list[float]] = {}
    for ticker in tickers:
        inst_id = inst_map.get(ticker)
        if inst_id:
            bar_stmt = (
                select(PriceBar.close)
                .where(PriceBar.instrument_id == inst_id)
                .order_by(PriceBar.ts)
            )
            rows = (await session.execute(bar_stmt)).scalars().all()
            if rows:
                daily_dict[ticker] = [float(r) for r in rows]

    min_len = min((len(v) for v in daily_dict.values()), default=0)
    if min_len < 10 or len(daily_dict) < len(tickers):
        raise DataUnavailableError("Insufficient price history for Black-Litterman optimization.")

    clean_dict = {t: v[-min_len:] for t, v in daily_dict.items()}
    prices_df = pd.DataFrame(clean_dict)
    ret_df = prices_df.pct_change().dropna()

    return compute_black_litterman_portfolio(
        ret_df,
        market_weights=body.market_weights,
        views=body.views,
        risk_aversion=body.risk_aversion,
        tau=body.tau,
        risk_free_rate=body.risk_free_rate,
    )


@router.post(
    "/{portfolio_id}/attribution", summary="Brinson-Fachler sector performance attribution"
)
async def sector_attribution_endpoint(
    portfolio_id: uuid.UUID,
    body: AttributionRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)
    enriched = await enrich_holdings_with_prices(session, holdings)

    start = body.start or (datetime.now(UTC).date() - timedelta(days=30))
    end = body.end or datetime.now(UTC).date()
    tickers = [h.ticker for h in holdings]
    inst_stmt = select(Instrument).where(Instrument.ticker.in_(tickers))
    inst_rows = (await session.execute(inst_stmt)).scalars().all()
    sectors = {inst.ticker: inst.sector or "Unclassified" for inst in inst_rows}
    histories, _missing, _ = await load_price_histories(
        session, tickers, base_currency=port.base_currency, start=start, end=end
    )
    return compute_sector_attribution(
        enriched,
        histories,
        sectors=sectors,
        benchmark_groups=body.benchmark_groups,
        start=start,
        end=end,
        method=body.method,
    )


@router.post("/{portfolio_id}/stress-test", summary="Historical macro stress shock scenarios")
async def stress_test_portfolio(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    tx_stmt = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == port.id)
    txs = (await session.execute(tx_stmt)).scalars().all()
    holdings = compute_holdings_fifo(txs)
    enriched = await enrich_holdings_with_prices(session, holdings)

    tot_val = sum((h.market_value or Decimal(0)) for h in enriched)
    if tot_val <= Decimal(0):
        tot_val = sum((h.total_cost for h in enriched), Decimal(0))
    if tot_val <= Decimal(0):
        tot_val = Decimal("100000.00")
    return execute_stress_tests(enriched, tot_val)


@router.delete("/{portfolio_id}", status_code=204, summary="Delete portfolio")
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    port = await session.get(Portfolio, portfolio_id)
    if not port or port.tenant_id != current_user.tenant_id:
        raise NotFoundError("Portfolio not found.")

    await session.delete(port)
    await session.commit()
