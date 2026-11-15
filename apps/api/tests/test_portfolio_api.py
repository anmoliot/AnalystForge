"""Tests for portfolio management, transaction tracking (FIFO), CSV import, risk analytics, and optimization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import io
import uuid
import httpx
import pytest
from sqlalchemy import select

from analystforge.api.db import Database
from analystforge.api.models.market import Exchange, Instrument, PriceBar


async def _seed_portfolio_prices(db: Database, tickers: list[str]) -> None:
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
                    sector="Technology",
                    is_active=True,
                )
                session.add(inst)
                await session.flush()

            # Seed 30 daily price bars with distinct variations per ticker
            start_dt = datetime(2024, 1, 1, tzinfo=UTC)
            ticker_mult = {"AAPL": 0.8, "MSFT": 1.4, "GOOGL": 0.5, "AMZN": 1.1}.get(ticker, 1.0)
            base_p = {"AAPL": 150.0, "MSFT": 350.0, "GOOGL": 140.0, "AMZN": 170.0}.get(ticker, 100.0)
            for i in range(30):
                dt = start_dt + timedelta(days=i)
                noise = ((i % 5) - 2) * 0.7 * ticker_mult
                val = Decimal(str(round(base_p + (i * 0.5 * ticker_mult) + noise, 2)))
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
                    provider="yahoo",
                )
                session.add(bar)
        await session.commit()


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"pm_{uuid.uuid4().hex[:6]}@hedgefund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Portfolio Manager",
            "tenant_name": "Alpha Capital",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_portfolio_lifecycle_and_transactions(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Create a portfolio
    create_resp = await client.post(
        "/api/v1/portfolios",
        headers=auth_headers,
        json={
            "name": "Global Tech Alpha",
            "description": "Long tech focused institutional fund",
            "base_currency": "USD",
            "benchmark_ticker": "SPY",
            "cost_basis_method": "FIFO",
        },
    )
    assert create_resp.status_code == 201
    port_id = create_resp.json()["id"]

    # 2. List portfolios
    list_resp = await client.get("/api/v1/portfolios", headers=auth_headers)
    assert list_resp.status_code == 200
    ports = list_resp.json()
    assert any(p["id"] == port_id for p in ports)

    # 3. Add BUY transactions (Lot 1: 100 shares @ $150; Lot 2: 50 shares @ $180)
    tx1_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": "2024-01-15",
            "quantity": 100.0,
            "price": 150.0,
            "currency": "USD",
            "commission": 0.0,
        },
    )
    assert tx1_resp.status_code == 201

    tx2_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": "2024-02-15",
            "quantity": 50.0,
            "price": 180.0,
            "currency": "USD",
            "commission": 0.0,
        },
    )
    assert tx2_resp.status_code == 201

    # 4. Add a SELL transaction (sell 120 shares - depletes Lot 1 of 100 and takes 20 from Lot 2)
    # Remaining: 30 shares from Lot 2 @ $180 cost basis = $5,400 total cost
    tx3_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={
            "ticker": "AAPL",
            "transaction_type": "SELL",
            "trade_date": "2024-03-01",
            "quantity": 120.0,
            "price": 190.0,
            "currency": "USD",
            "commission": 0.0,
        },
    )
    assert tx3_resp.status_code == 201

    # Add another ticker
    tx4_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={
            "ticker": "MSFT",
            "transaction_type": "BUY",
            "trade_date": "2024-01-20",
            "quantity": 40.0,
            "price": 400.0,
            "currency": "USD",
            "commission": 0.0,
        },
    )
    assert tx4_resp.status_code == 201

    # 5. Get portfolio with computed FIFO holdings
    get_resp = await client.get(f"/api/v1/portfolios/{port_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    p_data = get_resp.json()
    assert len(p_data["holdings"]) == 2

    aapl_holding = next(h for h in p_data["holdings"] if h["ticker"] == "AAPL")
    assert aapl_holding["shares"] == 30.0
    assert abs(aapl_holding["cost_basis"] - 180.0) < 0.01
    assert abs(aapl_holding["total_cost"] - 5400.0) < 0.01

    msft_holding = next(h for h in p_data["holdings"] if h["ticker"] == "MSFT")
    assert msft_holding["shares"] == 40.0
    assert abs(msft_holding["cost_basis"] - 400.0) < 0.01

    # 6. List transactions
    txs_list_resp = await client.get(
        f"/api/v1/portfolios/{port_id}/transactions", headers=auth_headers
    )
    assert txs_list_resp.status_code == 200
    assert len(txs_list_resp.json()) == 4

    # 7. Delete portfolio
    del_resp = await client.delete(f"/api/v1/portfolios/{port_id}", headers=auth_headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_csv_transaction_import(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Create portfolio
    port = (
        await client.post(
            "/api/v1/portfolios",
            headers=auth_headers,
            json={"name": "CSV Import Portfolio"},
        )
    ).json()
    port_id = port["id"]

    # 2. Valid CSV upload
    valid_csv = (
        "Date,Ticker,Type,Quantity,Price,Currency,Commission,Notes\n"
        "2024-01-10,NVDA,BUY,10,500.0,USD,0,Initial position\n"
        "2024-02-10,GOOGL,BUY,25,140.0,USD,0,Search position\n"
        "2024-03-01,NVDA,BUY,5,600.0,USD,0,Add to position\n"
    )
    files = {"file": ("trades.csv", io.BytesIO(valid_csv.encode("utf-8")), "text/csv")}
    upload_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/import",
        headers=auth_headers,
        files=files,
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["status"] == "success"
    assert data["imported_count"] == 3
    assert data["error_count"] == 0

    # Verify holdings
    detail_resp = await client.get(f"/api/v1/portfolios/{port_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    holdings = detail_resp.json()["holdings"]
    tickers = {h["ticker"] for h in holdings}
    assert "NVDA" in tickers
    assert "GOOGL" in tickers

    # 3. Malformed CSV upload (missing required columns)
    bad_csv = "InvalidCol1,InvalidCol2\n123,456\n"
    bad_files = {"file": ("bad.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}
    bad_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/import",
        headers=auth_headers,
        files=bad_files,
    )
    assert bad_resp.status_code == 422


@pytest.mark.asyncio
async def test_portfolio_risk_analytics_and_stress_test(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    # 1. Create portfolio with multiple assets
    port = (
        await client.post(
            "/api/v1/portfolios",
            headers=auth_headers,
            json={"name": "Risk & Stress Test Portfolio"},
        )
    ).json()
    port_id = port["id"]

    for ticker, qty, price in [("AAPL", 50, 180.0), ("MSFT", 30, 410.0), ("AMZN", 40, 175.0)]:
        await client.post(
            f"/api/v1/portfolios/{port_id}/transactions",
            headers=auth_headers,
            json={
                "ticker": ticker,
                "transaction_type": "BUY",
                "trade_date": "2024-01-02",
                "quantity": qty,
                "price": price,
            },
        )

    # 2. Verify explicit 422 DataUnavailable state before price ingestion
    unavail_resp = await client.get(f"/api/v1/portfolios/{port_id}/risk", headers=auth_headers)
    assert unavail_resp.status_code == 422
    assert unavail_resp.json()["error"]["code"] == "data_unavailable"

    # Seed real price history
    await _seed_portfolio_prices(db, ["AAPL", "MSFT", "AMZN"])

    # 3. Risk endpoint with real prices
    risk_resp = await client.get(f"/api/v1/portfolios/{port_id}/risk", headers=auth_headers)
    assert risk_resp.status_code == 200
    risk = risk_resp.json()
    assert "volatility" in risk
    assert "max_drawdown" in risk
    assert "var_95_hist" in risk
    assert "var_95_param" in risk
    assert "cvar_95" in risk

    # 4. Stress test endpoint
    stress_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/stress-test", headers=auth_headers
    )
    assert stress_resp.status_code == 200
    scenarios = stress_resp.json()
    assert len(scenarios) >= 4
    for sc in scenarios:
        assert "name" in sc
        assert "shock_pct" in sc
        assert "projected_loss" in sc
        assert "post_shock_value" in sc
        assert sc["projected_loss"] <= 0  # Losses are negative or non-positive


@pytest.mark.asyncio
async def test_portfolio_optimization(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    # 1. Create portfolio
    port = (
        await client.post(
            "/api/v1/portfolios",
            headers=auth_headers,
            json={"name": "Optimization Portfolio"},
        )
    ).json()
    port_id = port["id"]

    for ticker, qty, price in [("AAPL", 50, 180.0), ("MSFT", 30, 410.0), ("GOOGL", 40, 140.0)]:
        await client.post(
            f"/api/v1/portfolios/{port_id}/transactions",
            headers=auth_headers,
            json={
                "ticker": ticker,
                "transaction_type": "BUY",
                "trade_date": "2024-01-02",
                "quantity": qty,
                "price": price,
            },
        )

    # Verify explicit 422 DataUnavailable before price seeding
    unavail_opt = await client.post(
        f"/api/v1/portfolios/{port_id}/optimize?objective=max_sharpe",
        headers=auth_headers,
    )
    assert unavail_opt.status_code == 422
    assert unavail_opt.json()["error"]["code"] == "data_unavailable"

    # Seed real prices
    await _seed_portfolio_prices(db, ["AAPL", "MSFT", "GOOGL"])

    # 2. Max Sharpe Optimization
    opt_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/optimize?objective=max_sharpe",
        headers=auth_headers,
    )
    assert opt_resp.status_code == 200
    opt_data = opt_resp.json()
    assert "weights" in opt_data
    assert "expected_return" in opt_data
    assert "expected_volatility" in opt_data
    assert "sharpe" in opt_data
    assert "frontier" in opt_data
    assert len(opt_data["weights"]) == 3
    # Weights sum to approx 1.0
    tot_weight = sum(opt_data["weights"].values())
    assert abs(tot_weight - 1.0) < 0.05

    # 3. Min Variance Optimization
    min_var_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/optimize?objective=min_variance",
        headers=auth_headers,
    )
    assert min_var_resp.status_code == 200
    min_data = min_var_resp.json()
    assert "weights" in min_data
    assert len(min_data["weights"]) == 3
