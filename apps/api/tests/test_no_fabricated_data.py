"""Repository-wide guard ensuring zero fabricated or random data exists in analysis paths.

Mandated by WP1: fails if `random` / `np.random` / `Math.random` is used outside
`packages/quant` simulation functions that take an explicit seed, and outside `tests/`.
Also asserts that missing prices produce HTTP 422 `DataUnavailable` errors, never numbers.
"""

from __future__ import annotations

from pathlib import Path
import re
import uuid
import httpx
import pytest

from analystforge.api.db import Database


REPO_ROOT = Path(__file__).resolve().parent.parent

# Allowed exceptions: quant/services simulation functions that take an explicit seed parameter
ALLOWED_SIMULATION_FILES = {
    REPO_ROOT / "packages" / "quant" / "src" / "analystforge" / "quant" / "risk.py",
    REPO_ROOT / "apps" / "api" / "src" / "analystforge" / "api" / "services" / "valuation.py",
}

DISALLOWED_PATTERNS = [
    re.compile(r"\bnp\.random\.(?!default_rng)"),  # legacy global np.random calls
    re.compile(r"\bnp\.random\.seed\b"),
    re.compile(r"\bMath\.random\b"),
    re.compile(r"\brandom\.(random|normalvariate|randint|choice|sample|shuffle|uniform)\b"),
]


def test_no_random_or_fabricated_data_in_codebase() -> None:
    """Scans all production source files for unauthorized random generation."""
    violations: list[str] = []

    scan_dirs = [
        REPO_ROOT / "apps" / "api" / "src",
        REPO_ROOT / "apps" / "worker" / "src",
        REPO_ROOT / "apps" / "web" / "src",
        REPO_ROOT / "packages" / "quant" / "src",
        REPO_ROOT / "packages" / "providers" / "src",
        REPO_ROOT / "packages" / "sdk-python" / "src",
    ]

    for s_dir in scan_dirs:
        if not s_dir.exists():
            continue
        for path in s_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".js"}:
                continue
            if "test" in path.name.lower() or "conftest" in path.name.lower():
                continue
            if path in ALLOWED_SIMULATION_FILES:
                continue

            content = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in DISALLOWED_PATTERNS:
                for line_no, line in enumerate(content.splitlines(), start=1):
                    # Skip comments
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                        continue
                    if pattern.search(line):
                        violations.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}")

    assert not violations, (
        "Non-negotiable rule violation: Random/fabricated data generator found in production code:\n"
        + "\n".join(violations)
    )


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"guard_{uuid.uuid4().hex[:6]}@fund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Guard Tester",
            "tenant_name": "Guard Tenant",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_missing_prices_produce_data_unavailable(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    # 1. Backtest with no price bars returns 422 DataUnavailable, never numbers
    bt_resp = await client.post(
        "/api/v1/backtests/run",
        headers=auth_headers,
        json={
            "ticker": "NO_DATA_TICKER",
            "strategy_name": "BUY_AND_HOLD",
            "initial_capital": 50000.0,
            "commission": 1.0,
        },
    )
    assert bt_resp.status_code == 422
    bt_err = bt_resp.json()
    assert bt_err["error"]["code"] == "data_unavailable"
    assert "Minimum 30 daily price bars required" in bt_err["error"]["message"]

    # 2. Portfolio risk analytics with unpriced assets returns 422 DataUnavailable, never synthetic returns
    port = (
        await client.post(
            "/api/v1/portfolios",
            headers=auth_headers,
            json={"name": "Unpriced Portfolio"},
        )
    ).json()
    port_id = port["id"]

    await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={
            "ticker": "UNPRICED1",
            "transaction_type": "BUY",
            "trade_date": "2024-01-02",
            "quantity": 10.0,
            "price": 100.0,
        },
    )
    await client.post(
        f"/api/v1/portfolios/{port_id}/transactions",
        headers=auth_headers,
        json={
            "ticker": "UNPRICED2",
            "transaction_type": "BUY",
            "trade_date": "2024-01-02",
            "quantity": 20.0,
            "price": 50.0,
        },
    )

    risk_resp = await client.get(f"/api/v1/portfolios/{port_id}/risk", headers=auth_headers)
    assert risk_resp.status_code == 422
    risk_err = risk_resp.json()
    assert risk_err["error"]["code"] == "data_unavailable"
    assert "Insufficient price history" in risk_err["error"]["message"]

    # 3. Portfolio optimizer with unpriced assets returns 422 DataUnavailable, never np.random seed 42 fallback
    opt_resp = await client.post(
        f"/api/v1/portfolios/{port_id}/optimize?objective=max_sharpe",
        headers=auth_headers,
    )
    assert opt_resp.status_code == 422
    opt_err = opt_resp.json()
    assert opt_err["error"]["code"] == "data_unavailable"
    assert "portfolio optimization" in opt_err["error"]["message"]


@pytest.mark.asyncio
async def test_valuation_monte_carlo_explicit_seed(client: httpx.AsyncClient) -> None:
    # Verify that valuation Monte Carlo accepts explicit seed and returns it
    payload = {
        "ticker": "AAPL",
        "base_revenue": 1000.0,
        "revenue_growth": [0.08, 0.07, 0.06, 0.05, 0.04],
        "ebit_margin": [0.25],
        "tax_rate": 0.21,
        "wacc": 0.09,
        "terminal_growth": 0.025,
        "net_debt": 500.0,
        "shares_outstanding": 100.0,
    }

    r1 = await client.post("/api/v1/valuation/dcf/montecarlo?iterations=200&seed=123", json=payload)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["seed"] == 123

    r2 = await client.post("/api/v1/valuation/dcf/montecarlo?iterations=200&seed=999", json=payload)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["seed"] == 999

    # Different seeds must produce different Monte Carlo distributions
    assert d1["p50"] != d2["p50"]
