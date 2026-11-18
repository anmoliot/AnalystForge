"""Tests for valuation workbench endpoints (DCF calculation, sensitivity, Monte Carlo, Excel export, and model persistence)."""

from __future__ import annotations

import httpx
import pytest


@pytest.fixture
def sample_dcf_payload() -> dict:
    return {
        "ticker": "AAPL",
        "base_revenue": 1000.0,
        "revenue_growth": [0.10, 0.08, 0.06, 0.05, 0.04],
        "ebit_margin": [0.25],
        "tax_rate": 0.21,
        "wacc": 0.09,
        "terminal_growth": 0.025,
        "shares_outstanding": 100.0,
        "depreciation_pct_revenue": 0.04,
        "capex_pct_revenue": 0.05,
        "nwc_pct_incremental_revenue": 0.10,
        "net_debt": 50.0,
        "mid_year_convention": False,
        "terminal_method": "gordon_growth",
    }


@pytest.mark.asyncio
async def test_dcf_calculation_matches_reference(
    client: httpx.AsyncClient, sample_dcf_payload: dict
) -> None:
    resp = await client.post("/api/v1/valuation/dcf", json=sample_dcf_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["enterprise_value"] > 0
    assert data["equity_value"] > 0
    assert data["value_per_share"] > 0
    assert len(data["forecast"]) == 5

    # Check that equity value = enterprise value - net debt
    expected_equity = data["enterprise_value"] - sample_dcf_payload["net_debt"]
    assert abs(data["equity_value"] - expected_equity) < 0.01

    # Check that value per share = equity value / shares
    expected_vps = data["equity_value"] / sample_dcf_payload["shares_outstanding"]
    assert abs(data["value_per_share"] - expected_vps) < 0.01


@pytest.mark.asyncio
async def test_dcf_sensitivity_grid(client: httpx.AsyncClient, sample_dcf_payload: dict) -> None:
    resp = await client.post("/api/v1/valuation/dcf/sensitivity", json=sample_dcf_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "wacc_axis" in data
    assert "g_axis" in data
    assert "matrix" in data
    assert len(data["matrix"]) == len(data["wacc_axis"])
    assert len(data["matrix"][0]) == len(data["g_axis"])


@pytest.mark.asyncio
async def test_dcf_monte_carlo(client: httpx.AsyncClient, sample_dcf_payload: dict) -> None:
    resp = await client.post(
        "/api/v1/valuation/dcf/montecarlo?iterations=200", json=sample_dcf_payload
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "mean" in data
    assert "p10" in data
    assert "p50" in data
    assert "p90" in data
    assert data["p10"] <= data["p50"] <= data["p90"]


@pytest.mark.asyncio
async def test_dcf_excel_export(client: httpx.AsyncClient, sample_dcf_payload: dict) -> None:
    resp = await client.post("/api/v1/valuation/dcf/export/excel", json=sample_dcf_payload)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert len(resp.content) > 1000  # Non-trivial workbook binary


@pytest.mark.asyncio
async def test_valuation_model_persistence_and_versioning(
    client: httpx.AsyncClient, sample_dcf_payload: dict
) -> None:
    # 1. Register & login
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "val_analyst@fund.com",
            "password": "Password123!",
            "full_name": "Valuation Specialist",
            "tenant_name": "Valuation Fund",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "val_analyst@fund.com", "password": "Password123!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Compute DCF
    dcf_res = (await client.post("/api/v1/valuation/dcf", json=sample_dcf_payload)).json()

    # 3. Save Model
    save_payload = {
        "ticker": "AAPL",
        "name": "Apple Base DCF Model 2024",
        "model_type": "DCF",
        "scenario": "base",
        "assumptions": sample_dcf_payload,
        "results": dcf_res,
        "notes": "Initial base case DCF with 9% WACC.",
    }
    save_resp = await client.post("/api/v1/valuation/models", headers=headers, json=save_payload)
    assert save_resp.status_code == 201
    model_id = save_resp.json()["model_id"]

    # 4. List Models
    list_resp = await client.get("/api/v1/valuation/models", headers=headers)
    assert list_resp.status_code == 200
    models = list_resp.json()
    assert len(models) == 1
    assert models[0]["ticker"] == "AAPL"

    # 5. Add a Bull Version
    bull_payload = dict(sample_dcf_payload)
    bull_payload["revenue_growth"] = [0.15, 0.12, 0.10, 0.08, 0.06]
    bull_res = (await client.post("/api/v1/valuation/dcf", json=bull_payload)).json()

    v_resp = await client.post(
        f"/api/v1/valuation/models/{model_id}/versions",
        headers=headers,
        json={
            "scenario": "bull",
            "assumptions": bull_payload,
            "results": bull_res,
            "notes": "Accelerated growth case.",
        },
    )
    assert v_resp.status_code == 201
    assert v_resp.json()["version_number"] == 2

    # 6. Retrieve Model with Version History
    get_resp = await client.get(f"/api/v1/valuation/models/{model_id}", headers=headers)
    assert get_resp.status_code == 200
    model_data = get_resp.json()
    assert len(model_data["versions"]) == 2
    assert model_data["versions"][0]["version_number"] == 2
    assert model_data["versions"][0]["scenario"] == "bull"

    # 7. Delete Model
    del_resp = await client.delete(f"/api/v1/valuation/models/{model_id}", headers=headers)
    assert del_resp.status_code == 204
