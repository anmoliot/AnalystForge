"""Tests for Report Generation and Download API (Phase 10)."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"reports_analyst_{uuid.uuid4().hex[:6]}@morganstanley.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Senior Equity Research Analyst",
            "tenant_name": "Morgan Stanley Equities",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_report_generation_lifecycle(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    # 1. Generate report
    gen_resp = await client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={
            "title": "NVIDIA Institutional Tearsheet",
            "report_type": "TEARSHEET",
            "ticker": "NVDA",
            "format": "MARKDOWN",
        },
    )
    assert gen_resp.status_code == 200
    report_data = gen_resp.json()
    assert report_data["title"] == "NVIDIA Institutional Tearsheet"
    assert report_data["status"] == "COMPLETED"
    report_id = report_data["id"]

    # 2. List reports
    list_resp = await client.get("/api/v1/reports", headers=auth_headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(r["id"] == report_id for r in items)

    # 3. Get report details
    detail_resp = await client.get(f"/api/v1/reports/{report_id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert "Institutional Equity Tearsheet" in detail["content"]

    # 4. Download report
    down_resp = await client.get(f"/api/v1/reports/{report_id}/download", headers=auth_headers)
    assert down_resp.status_code == 200
    assert "attachment;" in down_resp.headers.get("content-disposition", "")
    assert b"Institutional Equity Tearsheet" in down_resp.content
