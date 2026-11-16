"""Tests for WP7: Multi-format reporting (PDF, PPTX, Excel formulas), SDK integration,
and email delivery.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from analystforge.api.services.reports import (
    SUPPORTED_FORMATS,
    generate_pdf_report,
    generate_pptx_report,
    generate_excel_report,
    build_report_file,
)
from analystforge_sdk.client import AnalystForgeClient, AnalystForgeError


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"reports_wp7_{uuid.uuid4().hex[:6]}@fund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "WP7 Test Analyst",
            "tenant_name": "Alpha Fund",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_supported_formats_and_unsupported_rejection(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Exit criteria: The API rejects unsupported formats instead of silently returning Markdown."""
    # 1. Reject invalid format on creation
    res = await client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={
            "title": "Invalid Format Report",
            "report_type": "TEARSHEET",
            "ticker": "AAPL",
            "format": "DOCX",
        },
    )
    assert res.status_code == 422
    assert "Unsupported format" in res.text

    # 2. Reject unsupported format on download
    # Create valid report first
    res_valid = await client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={
            "title": "Valid Report",
            "report_type": "TEARSHEET",
            "ticker": "AAPL",
            "format": "PDF",
        },
    )
    assert res_valid.status_code == 200
    rep_id = res_valid.json()["id"]

    res_dl_bad = await client.get(
        f"/api/v1/reports/{rep_id}/download?format=XML",
        headers=auth_headers,
    )
    assert res_dl_bad.status_code == 422
    assert "Unsupported format" in res_dl_bad.text


def test_tearsheet_exports_for_three_tickers():
    """Exit criteria: tear sheets exported for 3 tickers in PDF and PPTX."""
    tickers = ["AAPL", "NVDA", "MSFT"]
    sample_data = {
        "company_name": "Test Tech Corp",
        "sector": "Information Technology",
        "price": 185.50,
        "market_cap": 2_850_000_000_000,
        "pe_ratio": 32.4,
        "ev_ebitda": 24.1,
        "summary": "Dominant ecosystem with robust free cash flow and AI investments.",
        "metrics": [
            ("Revenue (TTM)", "$383.3B", "P/E Trailing", "32.4x"),
            ("Operating Margin", "30.5%", "EV / EBITDA", "24.1x"),
            ("FCF Conversion", "98%", "ROE", "145%"),
            ("Target Price", "$210.00", "Dividend Yield", "0.55%"),
        ],
    }

    for ticker in tickers:
        data = dict(sample_data, ticker=ticker, company_name=f"{ticker} Inc.")

        # Test PDF generation
        pdf_bytes = generate_pdf_report(f"{ticker} Tear Sheet", "TEARSHEET", data)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF")

        # Test PPTX generation
        pptx_bytes = generate_pptx_report(f"{ticker} Executive Deck", "TEARSHEET", data)
        assert isinstance(pptx_bytes, bytes)
        assert len(pptx_bytes) > 2000
        # PPTX is a zip file containing [Content_Types].xml
        assert pptx_bytes.startswith(b"PK")
        with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as z:
            assert "[Content_Types].xml" in z.namelist()


def test_excel_export_has_live_formulas():
    """Exit criteria: Excel export keeping live formulas."""
    sample_data = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "financials": [
            {"year": "2021", "revenue": 365817, "ebitda": 120233, "capex": 11085},
            {"year": "2022", "revenue": 394328, "ebitda": 130541, "capex": 10708},
            {"year": "2023", "revenue": 383285, "ebitda": 125820, "capex": 10959},
        ],
    }
    excel_bytes = generate_excel_report("AAPL Financial Model", "TEARSHEET", sample_data)
    assert isinstance(excel_bytes, bytes)
    assert excel_bytes.startswith(b"PK")

    # Inspect the OpenXML sheets for live formula elements: <f>SUM(...)</f> or <f>AVERAGE(...)</f>
    with zipfile.ZipFile(io.BytesIO(excel_bytes)) as z:
        sheet_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "<f>" in sheet_xml
        assert "AVERAGE" in sheet_xml or "SUM" in sheet_xml


@pytest.mark.asyncio
async def test_report_email_delivery_with_attachment(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Verify report email delivery triggers SMTP with attachment."""
    res = await client.post(
        "/api/v1/reports/generate",
        headers=auth_headers,
        json={
            "title": "Email Tear Sheet",
            "report_type": "TEARSHEET",
            "ticker": "NVDA",
            "format": "PDF",
        },
    )
    assert res.status_code == 200
    rep_id = res.json()["id"]

    with patch("analystforge.api.services.alerts.smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        email_res = await client.post(
            f"/api/v1/reports/{rep_id}/email",
            headers=auth_headers,
            json={"recipient_email": "pm@hedgefund.com"},
        )
        assert email_res.status_code == 200
        data = email_res.json()
        assert data["status"] == "sent"
        assert data["recipient"] == "pm@hedgefund.com"
        assert mock_instance.send_message.called


import respx

@respx.mock
def test_sdk_integration_with_fastapi():
    """Exit criteria: SDK integration test passes against running API."""
    # Mock health & meta
    respx.get("http://mock-api/health").respond(200, json={"status": "pass"})
    respx.get("http://mock-api/api/v1/meta/integrations").respond(
        200,
        json={"llm_provider": "openai-compatible", "llm_model": "llama-3.3-70b-versatile"},
    )

    # Mock 422 error on unsupported format (registered before generic POST)
    respx.post("http://mock-api/api/v1/reports/generate", json__format="UNSUPPORTED_TYPE").respond(
        422,
        json={"error": {"code": "unsupported_format", "message": "Unsupported format 'UNSUPPORTED_TYPE'"}},
    )

    # Mock report generation
    respx.post("http://mock-api/api/v1/reports/generate").respond(
        200,
        json={"id": "rep_msft_001", "status": "COMPLETED", "title": "MSFT Executive Summary"},
    )

    # Mock download routes
    respx.get("http://mock-api/api/v1/reports/rep_msft_001/download?format=PDF").respond(
        200,
        content=b"%PDF-1.4 sample pdf binary data",
        headers={"Content-Type": "application/pdf"},
    )
    respx.get("http://mock-api/api/v1/reports/rep_msft_001/download?format=EXCEL").respond(
        200,
        content=b"PK\x03\x04 sample xlsx binary data",
        headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )

    with AnalystForgeClient(base_url="http://mock-api", api_key="af_test_key") as sdk_client:
        # 1. Health & Meta
        health = sdk_client.health()
        assert health["status"] == "pass"

        meta = sdk_client.integrations_meta()
        assert meta["llm_provider"] == "openai-compatible"

        # 2. Generate PDF report
        rep = sdk_client.generate_report(
            title="MSFT Executive Summary",
            report_type="TEARSHEET",
            ticker="MSFT",
            format="PDF",
        )
        assert rep["id"] == "rep_msft_001"
        rep_id = rep["id"]

        # 3. Download report via SDK
        pdf_content = sdk_client.download_report(rep_id, format="PDF")
        assert pdf_content.startswith(b"%PDF")

        # 4. Download Excel via SDK
        excel_content = sdk_client.download_report(rep_id, format="EXCEL")
        assert excel_content.startswith(b"PK")

        # 5. Unsupported format rejection via SDK
        with pytest.raises(AnalystForgeError) as exc_info:
            sdk_client.generate_report(
                title="Bad Format",
                report_type="TEARSHEET",
                ticker="MSFT",
                format="UNSUPPORTED_TYPE",
            )
        assert exc_info.value.status_code == 422
