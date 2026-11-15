"""Tests for equity screener, FRED macro indicators, and alerts (Phase 8)."""

from __future__ import annotations

import uuid
import httpx
import pytest


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
async def test_macro_dashboard_endpoints(client: httpx.AsyncClient) -> None:
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
