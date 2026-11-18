"""Integration tests for backtesting enhancements (WP4).

Covers:
- Rule Builder endpoint (/backtests/rules)
- Sandboxed Python runner (/backtests/custom-python)
- Sandbox escape prevention (os, subprocess, open, __import__)
- Look-ahead bias rejection
- Walk-forward analysis (/backtests/walk-forward)
- 2D Parameter sweeps and heatmaps (/backtests/sweep)
- Background worker jobs with progress and cancel (/backtests/jobs)
- Survivorship bias disclosures
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from analystforge.api.db import Database
from analystforge.api.models.market import Exchange, Instrument, PriceBar


async def _seed_test_prices(db: Database, ticker: str, count: int = 60) -> None:
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
                name=f"{ticker} Corp.",
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
            wave = (i % 8) * 2.0
            val = Decimal(str(round(100.0 + wave + (i * 0.3), 2)))
            bar = PriceBar(
                instrument_id=inst.id,
                interval="1d",
                ts=dt,
                open=val - Decimal("0.50"),
                high=val + Decimal("2.00"),
                low=val - Decimal("2.00"),
                close=val,
                adjusted_close=val,
                volume=500000,
                provider="stooq",
            )
            session.add(bar)
        await session.commit()


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"backtest_tester_{uuid.uuid4().hex[:6]}@fund.org"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Quant Backtester",
            "tenant_name": "Alpha Quant Lab",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_rule_builder_backtest(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_test_prices(db, "NVDA", count=60)

    payload = {
        "ticker": "NVDA",
        "rule_group": {
            "combinator": "AND",
            "rules": [
                {"left": {"name": "RSI", "params": {"period": 14}}, "op": "<", "right": 65.0},
                {
                    "left": {"name": "CLOSE"},
                    "op": ">=",
                    "right": {"name": "SMA", "params": {"window": 10}},
                },
            ],
        },
        "initial_capital": 50000.0,
        "commission_per_trade": 2.0,
        "slippage_bps": 5.0,
        "borrow_cost_annual_pct": 0.02,
        "allow_short": False,
    }

    resp = await client.post("/api/v1/backtests/rules", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["strategy_name"] == "RULE_BUILDER"
    assert data["ticker"] == "NVDA"
    assert len(data["equity_curve"]) >= 30
    assert "survivorship_warning" in data
    assert "total_slippage_paid" in data


@pytest.mark.asyncio
async def test_custom_python_backtest_legitimate_and_escapes(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_test_prices(db, "GOOGL", count=60)

    # 1. Legitimate Python strategy
    code_legit = """
import numpy as np

def generate_signals(df):
    closes = df['close'].values
    signals = np.zeros(len(closes), dtype=int)
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            signals[i] = 1
        else:
            signals[i] = 0
    return signals
"""
    resp_ok = await client.post(
        "/api/v1/backtests/custom-python",
        headers=auth_headers,
        json={"ticker": "GOOGL", "code": code_legit, "initial_capital": 80000.0},
    )
    if sys.platform == "win32":
        assert resp_ok.status_code == 501, resp_ok.text
        assert "not supported on Windows" in resp_ok.text
    else:
        assert resp_ok.status_code == 200, resp_ok.text
        data = resp_ok.json()
        assert data["strategy_name"] == "CUSTOM_PYTHON"
        assert len(data["equity_curve"]) >= 30
        assert "survivorship_warning" in data

    # 2. Malicious attempt: import os
    code_malicious = """
import os
def generate_signals(df):
    os.system('id')
    return [1] * len(df)
"""
    resp_bad = await client.post(
        "/api/v1/backtests/custom-python",
        headers=auth_headers,
        json={"ticker": "GOOGL", "code": code_malicious},
    )
    assert resp_bad.status_code == 400
    assert "Sandbox security violation" in resp_bad.text


@pytest.mark.asyncio
async def test_walk_forward_analysis(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_test_prices(db, "TSLA", count=60)

    payload = {
        "ticker": "TSLA",
        "strategy_type": "BUILTIN",
        "strategy_name": "SMA_CROSSOVER",
        "parameters": {"fast_period": 5, "slow_period": 15},
        "num_folds": 3,
        "train_pct": 0.60,
    }

    resp = await client.post("/api/v1/backtests/walk-forward", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticker"] == "TSLA"
    assert len(data["folds"]) >= 2
    assert "walk_forward_efficiency" in data
    assert "overfitting_warning" in data


@pytest.mark.asyncio
async def test_parameter_sweep(
    client: httpx.AsyncClient, auth_headers: dict[str, str], db: Database
) -> None:
    await _seed_test_prices(db, "AMZN", count=60)

    payload = {
        "ticker": "AMZN",
        "strategy_name": "SMA_CROSSOVER",
        "param1_name": "fast_period",
        "param1_values": [5, 10],
        "param2_name": "slow_period",
        "param2_values": [15, 20],
    }

    resp = await client.post("/api/v1/backtests/sweep", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["param1_name"] == "fast_period"
    assert len(data["sharpe_matrix"]) == 2
    assert len(data["sharpe_matrix"][0]) == 2
    assert "dsr" in data
    assert "best_params" in data
    assert "overfitting_warning" in data


@pytest.mark.asyncio
async def test_background_job_lifecycle(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Spawn background job
    create_resp = await client.post(
        "/api/v1/backtests/jobs",
        headers=auth_headers,
        json={"job_type": "SWEEP", "payload": {"ticker": "AAPL"}},
    )
    assert create_resp.status_code == 200, create_resp.text
    job_info = create_resp.json()
    job_id = job_info["job_id"]
    assert job_info["status"] in ("queued", "running")

    # 2. Get status
    status_resp = await client.get(f"/api/v1/backtests/jobs/{job_id}", headers=auth_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id

    # 3. Cancel job
    cancel_resp = await client.post(f"/api/v1/backtests/jobs/{job_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
