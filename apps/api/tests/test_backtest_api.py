"""Tests for quantitative backtest execution and run persistence (Phase 7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from analystforge.api.db import Database
from analystforge.api.models.market import Exchange, Instrument, PriceBar


async def _seed_backtest_prices(db: Database, ticker: str, count: int = 60) -> None:
    async with db.session() as session:
        ex = await session.get(Exchange, "NASDAQ")
        if not ex:
            session.add(
                Exchange(
                    code="NASDAQ",
                    name="Nasdaq",
                    country="US",
                    timezone="America/New_York",
                    currency="USD",
                )
            )
            await session.flush()

        inst = (
            await session.execute(select(Instrument).where(Instrument.ticker == ticker))
        ).scalar_one_or_none()
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

        start_dt = datetime(2024, 1, 1, tzinfo=UTC)
        for i in range(count):
            dt = start_dt + timedelta(days=i)
            # Up-and-down price pattern to generate SMA crossovers and RSI swings
            wave = (i % 10) * 1.5 if (i // 10) % 2 == 0 else (10 - (i % 10)) * 1.5
            val = Decimal(str(round(150.0 + wave + (i * 0.2), 2)))
            bar = PriceBar(
                instrument_id=inst.id,
                interval="1d",
                ts=dt,
                open=val,
                high=val + Decimal("2.00"),
                low=val - Decimal("2.00"),
                close=val + Decimal("0.10"),
                adjusted_close=val + Decimal("0.10"),
                volume=1000000,
                provider="yahoo",
            )
            session.add(bar)
        await session.commit()


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"quant_{uuid.uuid4().hex[:6]}@quantfund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Quant Researcher",
            "tenant_name": "Citadel Alpha",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_run_sma_crossover_backtest(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    # 0. Missing price history returns explicit 422 DataUnavailable
    bad_resp = await client.post(
        "/api/v1/backtests/run",
        headers=auth_headers,
        json={
            "ticker": "NONEXISTENT",
            "strategy_name": "SMA_CROSSOVER",
            "initial_capital": 50000.0,
            "commission": 1.0,
            "parameters": {"fast_period": 5, "slow_period": 20},
        },
    )
    assert bad_resp.status_code == 422
    assert bad_resp.json()["error"]["code"] == "data_unavailable"

    # Seed real AAPL prices
    await _seed_backtest_prices(db, "AAPL", count=60)

    # 1. Execute backtest run
    run_resp = await client.post(
        "/api/v1/backtests/run",
        headers=auth_headers,
        json={
            "ticker": "AAPL",
            "strategy_name": "SMA_CROSSOVER",
            "initial_capital": 50000.0,
            "commission": 1.0,
            "parameters": {"fast_period": 5, "slow_period": 20},
        },
    )
    assert run_resp.status_code == 200, run_resp.text
    run_data = run_resp.json()
    assert run_data["ticker"] == "AAPL"
    assert run_data["strategy_name"] == "SMA_CROSSOVER"
    assert run_data["initial_capital"] == 50000.0
    assert "total_return" in run_data
    assert "sharpe_ratio" in run_data
    assert "max_drawdown" in run_data
    assert "equity_curve" in run_data
    assert len(run_data["equity_curve"]) >= 30
    assert "trades" in run_data
    run_id = run_data["id"]

    # 2. List backtests
    list_resp = await client.get("/api/v1/backtests", headers=auth_headers)
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert any(r["id"] == run_id for r in runs)

    # 3. Get single backtest detail
    get_resp = await client.get(f"/api/v1/backtests/{run_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == run_id
    assert len(detail["equity_curve"]) == len(run_data["equity_curve"])

    # 4. Delete backtest
    del_resp = await client.delete(f"/api/v1/backtests/{run_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # 5. Confirm 404
    get_again = await client.get(f"/api/v1/backtests/{run_id}", headers=auth_headers)
    assert get_again.status_code == 404


@pytest.mark.asyncio
async def test_run_rsi_momentum_backtest(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_backtest_prices(db, "MSFT", count=60)
    run_resp = await client.post(
        "/api/v1/backtests/run",
        headers=auth_headers,
        json={
            "ticker": "MSFT",
            "strategy_name": "RSI_MOMENTUM",
            "initial_capital": 100000.0,
            "commission": 2.0,
            "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70},
        },
    )
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["strategy_name"] == "RSI_MOMENTUM"
    assert len(data["equity_curve"]) >= 30
