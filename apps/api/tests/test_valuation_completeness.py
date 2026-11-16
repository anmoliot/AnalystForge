"""Integration tests for complete valuation workbench endpoints (WP2)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_valuation_fcfe_api(client: httpx.AsyncClient) -> None:
    payload = {
        "ticker": "AAPL",
        "base_net_income": 1000.0,
        "net_income_growth": [0.10, 0.10, 0.10, 0.10, 0.10],
        "cost_of_equity": 0.10,
        "terminal_growth": 0.03,
        "shares_outstanding": 100.0,
        "depreciation_pct_ni": 0.15,
        "capex_pct_ni": 0.20,
        "nwc_pct_ni": 0.05,
        "net_borrowing_pct_ni": 0.10,
    }
    resp = await client.post("/api/v1/valuation/fcfe", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["equity_value"] > 0
    assert data["value_per_share"] > 0
    assert len(data["forecast"]) == 5
    # Reference value check: pv_explicit_fcfe == 5000.00
    assert abs(data["pv_explicit_fcfe"] - 5000.0) < 1.0


@pytest.mark.asyncio
async def test_valuation_ddm_gordon_and_multistage(client: httpx.AsyncClient) -> None:
    # 1. Single-stage Gordon
    gordon_payload = {
        "ticker": "KO",
        "model_type": "gordon",
        "dividend_t0": 4.0,
        "cost_of_equity": 0.09,
        "growth_rate": 0.04,
    }
    g_resp = await client.post("/api/v1/valuation/ddm", json=gordon_payload)
    assert g_resp.status_code == 200
    g_data = g_resp.json()
    assert abs(g_data["implied_share_price"] - 83.20) < 0.01

    # 2. Multi-stage
    multi_payload = {
        "ticker": "KO",
        "model_type": "multi_stage",
        "base_dividend": 2.0,
        "stage1_growth": [0.15, 0.15, 0.15],
        "cost_of_equity": 0.10,
        "terminal_growth": 0.04,
    }
    m_resp = await client.post("/api/v1/valuation/ddm", json=multi_payload)
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert abs(m_data["implied_share_price"] - 46.17) < 0.1
    assert len(m_data["forecast"]) == 3


@pytest.mark.asyncio
async def test_valuation_residual_income_api(client: httpx.AsyncClient) -> None:
    payload = {
        "ticker": "MSFT",
        "base_book_value": 50.0,
        "forecast_net_income": [10.0, 12.0],
        "cost_of_equity": 0.10,
        "shares_outstanding": 1.0,
        "dividend_payout_ratio": 0.20,
        "terminal_method": "gordon_growth",
        "terminal_growth": 0.02,
    }
    resp = await client.post("/api/v1/valuation/residual-income", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["equity_value"] - 125.0) < 0.1
    assert len(data["forecast"]) == 2


@pytest.mark.asyncio
async def test_valuation_comps_multiples(client: httpx.AsyncClient) -> None:
    payload = {
        "ticker": "GOOGL",
        "peer_multiples": [18.0, 20.0, 22.0, 25.0, 30.0],
        "target_metric": 5000.0,  # e.g. EBITDA $5,000M
        "net_debt": 10000.0,
        "shares_outstanding": 1000.0,
        "is_equity_multiple": False,
    }
    resp = await client.post("/api/v1/valuation/comps", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 5
    assert data["median_multiple"] == 22.0
    # Implied median: (5000 * 22 - 10000) / 1000 = (110000 - 10000) / 1000 = 100.0
    assert abs(data["implied_share_price_median"] - 100.0) < 0.01
    assert data["implied_share_price_min"] < data["implied_share_price_max"]


@pytest.mark.asyncio
async def test_valuation_sotp_api(client: httpx.AsyncClient) -> None:
    payload = {
        "ticker": "AMZN",
        "segments": [
            {"name": "Retail", "metric_name": "Revenue", "metric_value": 4000.0, "multiple": 2.0, "ownership_pct": 1.0},
            {"name": "AWS Cloud", "metric_name": "EBITDA", "metric_value": 1000.0, "multiple": 18.0, "ownership_pct": 1.0},
        ],
        "shares_outstanding": 100.0,
        "net_debt": 2000.0,
    }
    resp = await client.post("/api/v1/valuation/sotp", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Total EV = 4000*2 + 1000*18 = 8000 + 18000 = 26000
    assert data["total_enterprise_value"] == 26000.0
    # Equity value = 26000 - 2000 = 24000. Share price = 240.0
    assert data["equity_value"] == 24000.0
    assert data["implied_share_price"] == 240.0


@pytest.mark.asyncio
async def test_valuation_precedents_api(client: httpx.AsyncClient) -> None:
    payload = {
        "ticker": "CRWD",
        "deals": [
            {"target": "CyberOne", "announced_date": "2024-01-01", "deal_value": 1000.0, "target_metric": 100.0},
            {"target": "SecurityPro", "announced_date": "2024-06-01", "deal_value": 2400.0, "target_metric": 200.0},
        ],
        "target_metric": 150.0,
        "shares_outstanding": 50.0,
        "net_debt": 100.0,
    }
    resp = await client.post("/api/v1/valuation/precedents", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["deals"]) == 2
    assert data["implied_share_price_median"] > 0


@pytest.mark.asyncio
async def test_valuation_wacc_builder_api(client: httpx.AsyncClient) -> None:
    payload = {
        "raw_beta": 1.5,
        "apply_blume": True,
        "risk_free_rate": 0.04,
        "equity_risk_premium": 0.06,
        "pre_tax_cost_of_debt": 0.05,
        "tax_rate": 0.20,
        "market_value_equity": 800000.0,
        "market_value_debt": 200000.0,
    }
    resp = await client.post("/api/v1/valuation/wacc-builder", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Blume adjusted beta = (2/3)*1.5 + (1/3)*1.0 = 1.0 + 0.3333 = 1.3333
    assert abs(data["adjusted_beta"] - 1.3333) < 0.01
    # Cost of equity = 0.04 + 1.3333 * 0.06 = 0.04 + 0.08 = 0.12
    assert abs(data["cost_of_equity"] - 0.12) < 0.01
    # After-tax debt = 0.05 * 0.8 = 0.04
    assert data["after_tax_cost_of_debt"] == 0.04
    # WACC = 0.8 * 0.12 + 0.2 * 0.04 = 0.096 + 0.008 = 0.104 (10.4%)
    assert abs(data["wacc"] - 0.104) < 0.001


@pytest.mark.asyncio
async def test_valuation_football_field_api(client: httpx.AsyncClient) -> None:
    payload = {
        "ticker": "NVDA",
        "current_share_price": 140.0,
        "ranges": [
            {"method_id": "dcf_fcff", "label": "DCF (FCFF)", "category": "Intrinsic", "low": 130.0, "base": 150.0, "high": 170.0},
            {"method_id": "comps_pe", "label": "Comps P/E", "category": "Comps", "low": 120.0, "base": 145.0, "high": 165.0},
            {"method_id": "ddm", "label": "DDM", "category": "Intrinsic", "low": 110.0, "base": 135.0, "high": 155.0},
        ],
    }
    resp = await client.post("/api/v1/valuation/football-field", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["composite_low"] == 110.0
    assert data["composite_high"] == 170.0
    assert data["composite_median"] == 145.0
    assert len(data["ranges"]) == 3
