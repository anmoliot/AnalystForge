"""Tests for equity screener, FRED macro indicators, and alerts (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
import httpx
import pytest

from analystforge.api.db import Database
from analystforge.api.models.macro import FxRate, MacroObservation, MacroSeries


async def _seed_macro_data(db: Database) -> None:
    async with db.session() as session:
        today = date.today()
        series_info = [
            ("DGS10", "10-Year Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS2", "2-Year Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS1MO", "1-Month Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS3MO", "3-Month Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS6MO", "6-Month Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS1", "1-Year Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS5", "5-Year Treasury Constant Maturity Rate", "%", "Daily"),
            ("DGS30", "30-Year Treasury Constant Maturity Rate", "%", "Daily"),
            ("FEDFUNDS", "Federal Funds Effective Rate", "%", "Monthly"),
            ("CPIAUCSL", "Consumer Price Index (CPI All Urban)", "Index", "Monthly"),
            ("UNRATE", "Civilian Unemployment Rate", "%", "Monthly"),
            ("GDPC1", "Real Gross Domestic Product", "Bil. Chn. 2017 $", "Quarterly"),
        ]
        rates = {
            "DGS10": 4.35, "DGS2": 4.22, "DGS1MO": 4.60, "DGS3MO": 4.55,
            "DGS6MO": 4.45, "DGS1": 4.30, "DGS5": 4.18, "DGS30": 4.55,
            "FEDFUNDS": 4.83, "CPIAUCSL": 315.2, "UNRATE": 4.1, "GDPC1": 22850.0,
        }
        for code, title, units, freq in series_info:
            s = await session.get(MacroSeries, code)
            if not s:
                s = MacroSeries(code=code, title=title, units=units, frequency=freq, provider="FRED")
                session.add(s)
                await session.flush()

            val = Decimal(str(rates[code]))
            # Seed today, 1 month ago, 1 year ago
            for offset in (0, 30, 365):
                obs = MacroObservation(
                    series_code=code,
                    day=today - timedelta(days=offset),
                    value=val,
                    provider="fred",
                )
                session.add(obs)

        # FX pairs
        fx_pairs = [("EUR", "USD", Decimal("1.085")), ("GBP", "USD", Decimal("1.295")), ("USD", "JPY", Decimal("154.2"))]
        for b, q, r in fx_pairs:
            session.add(FxRate(base=b, quote=q, day=today, rate=r, provider="ecb"))

        await session.commit()


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"analyst_{uuid.uuid4().hex[:6]}@macrofund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Macro Analyst",
            "tenant_name": "Soros Macro Alpha",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_screener_execution_and_saved_preset(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Run screen
    resp = await client.post(
        "/api/v1/screener",
        headers=auth_headers,
        json={"min_price": 10.0, "max_pe": 50.0},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert isinstance(results, list)

    # 2. Save screen preset
    save_resp = await client.post(
        "/api/v1/screener/saved",
        headers=auth_headers,
        json={
            "name": "High Quality Tech",
            "description": "Tech stocks with PE under 35 and ROE > 15%",
            "filters": {"sector": "Technology", "max_pe": 35.0, "min_roe": 0.15},
        },
    )
    assert save_resp.status_code == 201
    preset_id = save_resp.json()["id"]

    # 3. List saved presets
    list_saved = await client.get("/api/v1/screener/saved", headers=auth_headers)
    assert list_saved.status_code == 200
    presets = list_saved.json()
    assert any(p["id"] == preset_id for p in presets)

    # 4. Delete saved preset
    del_resp = await client.delete(
        f"/api/v1/screener/saved/{preset_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_macro_dashboard_endpoints(client: httpx.AsyncClient, db: Database) -> None:
    await _seed_macro_data(db)

    # 1. Economic series
    series_resp = await client.get("/api/v1/macro/series")
    assert series_resp.status_code == 200
    series = series_resp.json()
    assert len(series) >= 5
    assert any(s["id"] == "DGS10" for s in series)

    # 2. Yield curve
    yc_resp = await client.get("/api/v1/macro/yield-curve")
    assert yc_resp.status_code == 200
    yc = yc_resp.json()
    assert "spread_10y_2y" in yc
    assert "is_inverted" in yc
    assert "curve" in yc
    assert len(yc["curve"]) >= 6

    # 3. FX rates
    fx_resp = await client.get("/api/v1/macro/fx")
    assert fx_resp.status_code == 200
    fx = fx_resp.json()
    assert len(fx) >= 3


@pytest.mark.asyncio
async def test_alert_rules_lifecycle(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Create alert rule
    create_resp = await client.post(
        "/api/v1/alerts/rules",
        headers=auth_headers,
        json={"ticker": "NVDA", "rule_type": "PRICE_ABOVE", "target_value": 150.0},
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    # 2. List alert rules
    rules_resp = await client.get("/api/v1/alerts/rules", headers=auth_headers)
    assert rules_resp.status_code == 200
    rules = rules_resp.json()
    assert any(r["id"] == rule_id for r in rules)

    # 3. List alert events
    events_resp = await client.get("/api/v1/alerts/events", headers=auth_headers)
    assert events_resp.status_code == 200
    assert isinstance(events_resp.json(), list)

    # 4. Delete alert rule
    del_resp = await client.delete(
        f"/api/v1/alerts/rules/{rule_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204
