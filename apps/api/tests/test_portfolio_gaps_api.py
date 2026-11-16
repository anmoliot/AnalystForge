"""Tests for portfolio gap closures: CSV/Excel import wizard, column mapping preview,
validation report, rebalance trade orders, Black-Litterman, turnover/sector caps,
Fama-French factor exposures, rolling stats, and Brinson attribution.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from analystforge.api.db import Database
from analystforge.api.models.market import Exchange, Instrument, PriceBar


async def _seed_test_portfolio_prices(db: Database, tickers: list[str]) -> None:
    async with db.session() as session:
        ex = await session.get(Exchange, "NASDAQ")
        if not ex:
            session.add(Exchange(code="NASDAQ", name="Nasdaq", country="US", timezone="America/New_York", currency="USD"))
            await session.flush()

        for ticker in tickers:
            inst = (await session.execute(select(Instrument).where(Instrument.ticker == ticker))).scalar_one_or_none()
            if not inst:
                inst = Instrument(
                    id=uuid.uuid4(),
                    exchange_code="NASDAQ",
                    ticker=ticker,
                    name=f"{ticker} Inc.",
                    asset_type="equity",
                    currency="USD",
                    sector="Technology" if ticker in ("AAPL", "MSFT") else "Healthcare",
                    is_active=True,
                )
                session.add(inst)
                await session.flush()

            # Seed 30 daily price bars with distinct variations per ticker
            start_dt = datetime(2024, 1, 1, tzinfo=UTC)
            base_p = {"AAPL": 150.0, "MSFT": 350.0, "SPY": 480.0, "UNH": 500.0}.get(ticker, 100.0)
            for i in range(30):
                dt = start_dt + timedelta(days=i)
                val = Decimal(str(round(base_p + (i * 0.5) + (i % 3), 2)))
                bar = PriceBar(
                    instrument_id=inst.id,
                    interval="1d",
                    ts=dt,
                    open=val,
                    high=val + Decimal("2.00"),
                    low=val - Decimal("2.00"),
                    close=val + Decimal("0.20"),
                    adjusted_close=val + Decimal("0.20"),
                    volume=1000000,
                    provider="test",
                )
                session.add(bar)
        await session.commit()


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"pm_gaps_{uuid.uuid4().hex[:6]}@quantfund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Portfolio Gaps PM",
            "tenant_name": "Quant Alpha",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_import_wizard_preview_and_mapping(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Verify import wizard preview detects columns and suggests mapping."""
    res_port = await client.post(
        "/api/v1/portfolios",
        headers=auth_headers,
        json={"name": "Wizard Portfolio", "benchmark_ticker": "SPY"},
    )
    assert res_port.status_code == 201
    port_id = res_port.json()["id"]

    # CSV with custom headers
    csv_data = "ExecutionDate,Symbol,Side,Shares,FillPrice\n2024-01-10,AAPL,BUY,100,150.00\n2024-01-11,MSFT,BUY,50,350.00"
    files = {"file": ("custom_tx.csv", csv_data.encode(), "text/csv")}

    preview_res = await client.post(
        f"/api/v1/portfolios/{port_id}/import/preview",
        headers=auth_headers,
        files=files,
    )
    assert preview_res.status_code == 200
    preview = preview_res.json()
    assert "ExecutionDate" in preview["headers"]
    assert "Symbol" in preview["headers"]
    assert len(preview["preview_rows"]) == 2

    # Execute import with explicit mapping
    mapping = {
        "date": "ExecutionDate",
        "ticker": "Symbol",
        "type": "Side",
        "quantity": "Shares",
        "price": "FillPrice",
    }
    files_import = {"file": ("custom_tx.csv", csv_data.encode(), "text/csv")}
    import_res = await client.post(
        f"/api/v1/portfolios/{port_id}/import",
        headers=auth_headers,
        data={"mapping": json.dumps(mapping)},
        files=files_import,
    )
    assert import_res.status_code == 200
    imp = import_res.json()
    assert imp["imported_count"] == 2
    assert imp["error_count"] == 0

    # Test download validation report
    report_res = await client.post(
        f"/api/v1/portfolios/{port_id}/import/download-report",
        headers=auth_headers,
        json=imp["validation_report"],
    )
    assert report_res.status_code == 200
    assert "text/csv" in report_res.headers["content-type"]


@pytest.mark.asyncio
async def test_rebalance_and_optimization_constraints(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    """Verify rebalance trade generation and optimization with turnover/sector caps."""
    tickers = ["AAPL", "MSFT", "SPY"]
    await _seed_test_portfolio_prices(db, tickers)

    res_port = await client.post(
        "/api/v1/portfolios",
        headers=auth_headers,
        json={"name": "Rebalance & Opt Portfolio", "benchmark_ticker": "SPY"},
    )
    port_id = res_port.json()["id"]

    # Add holdings
    await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={"ticker": "AAPL", "transaction_type": "BUY", "trade_date": "2024-01-02", "quantity": 100, "price": 150},
    )
    await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={"ticker": "MSFT", "transaction_type": "BUY", "trade_date": "2024-01-02", "quantity": 50, "price": 350},
    )

    # 1. Test Rebalance endpoint
    rebalance_res = await client.post(
        f"/api/v1/portfolios/{port_id}/rebalance",
        headers=auth_headers,
        json={
            "target_weights": {"AAPL": 0.50, "MSFT": 0.50},
            "cash": 5000.0,
            "commission_bps": 10.0,
        },
    )
    assert rebalance_res.status_code == 200
    reb = rebalance_res.json()
    assert "orders" in reb
    assert reb["turnover"] >= 0.0
    assert reb["total_traded_value"] > 0.0

    # 2. Test Optimization with turnover and sector caps
    opt_res = await client.post(
        f"/api/v1/portfolios/{port_id}/optimize",
        headers=auth_headers,
        json={
            "objective": "min_variance",
            "initial_weights": [0.5, 0.5],
            "turnover_cap": 0.20,
            "asset_sectors": ["Technology", "Technology"],
            "sector_caps": {"Technology": 1.0},
        },
    )
    assert opt_res.status_code == 200
    opt = opt_res.json()
    assert "weights" in opt
    assert opt["status"] in ("optimal", "optimal_inaccurate")


@pytest.mark.asyncio
async def test_factors_rolling_black_litterman_and_attribution(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    """Verify Fama-French factors, rolling stats, Black-Litterman, and Brinson attribution endpoints."""
    tickers = ["AAPL", "MSFT", "SPY"]
    await _seed_test_portfolio_prices(db, tickers)

    res_port = await client.post(
        "/api/v1/portfolios",
        headers=auth_headers,
        json={"name": "Analytics Portfolio", "benchmark_ticker": "SPY"},
    )
    port_id = res_port.json()["id"]

    await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={"ticker": "AAPL", "transaction_type": "BUY", "trade_date": "2024-01-02", "quantity": 100, "price": 150},
    )
    await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={"ticker": "MSFT", "transaction_type": "BUY", "trade_date": "2024-01-02", "quantity": 50, "price": 350},
    )

    # 1. Fama-French factor exposure
    factors_res = await client.get(
        f"/api/v1/portfolios/{port_id}/factors",
        headers=auth_headers,
    )
    assert factors_res.status_code == 200
    factors = factors_res.json()
    assert "betas" in factors
    assert "alpha_annualized" in factors
    assert "r_squared" in factors
    assert factors["observations"] >= 5

    # 2. Rolling statistics
    rolling_res = await client.get(
        f"/api/v1/portfolios/{port_id}/rolling?window=10",
        headers=auth_headers,
    )
    assert rolling_res.status_code == 200
    rolling = rolling_res.json()
    assert len(rolling["rolling_volatility"]) > 0
    assert len(rolling["dates"]) > 0

    # 3. Black-Litterman
    bl_res = await client.post(
        f"/api/v1/portfolios/{port_id}/black-litterman",
        headers=auth_headers,
        json={
            "market_weights": {"AAPL": 0.5, "MSFT": 0.5},
            "views": [
                {"assets": {"AAPL": 1.0, "MSFT": 0.0}, "expected_return": 0.15}
            ],
            "risk_aversion": 2.5,
        },
    )
    assert bl_res.status_code == 200
    bl = bl_res.json()
    assert "equilibrium_returns" in bl
    assert "posterior_returns" in bl
    assert "optimal_weights" in bl

    # 4. Brinson Sector Attribution
    attrib_res = await client.post(
        f"/api/v1/portfolios/{port_id}/attribution",
        headers=auth_headers,
        json={
            "start": "2024-01-02",
            "end": "2024-01-20",
            "benchmark_groups": [
                {"name": "Technology", "weight": 0.70, "return": 0.05},
                {"name": "Healthcare", "weight": 0.30, "return": 0.02},
            ],
        },
    )
    assert attrib_res.status_code == 200
    attrib = attrib_res.json()
    assert "active_return" in attrib
    assert "allocation" in attrib
    assert "selection" in attrib
