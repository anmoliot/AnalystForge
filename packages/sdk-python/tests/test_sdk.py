"""Unit tests for AnalystForge Python SDK client."""

import pytest
import respx
import httpx

from analystforge_sdk.client import AnalystForgeClient, AnalystForgeError


def test_client_context_manager():
    with AnalystForgeClient(base_url="http://mock-api") as client:
        assert client is not None


@respx.mock
def test_client_health_and_meta():
    respx.get("http://mock-api/health").respond(200, json={"status": "pass"})
    respx.get("http://mock-api/api/v1/meta").respond(200, json={"version": "0.1.0"})

    with AnalystForgeClient(base_url="http://mock-api") as client:
        health = client.health()
        assert health["status"] == "pass"

        meta = client.meta()
        assert meta["version"] == "0.1.0"


@respx.mock
def test_client_reporting_and_research():
    respx.post("http://mock-api/api/v1/research/query").respond(
        200,
        json={"answer": "Bullish", "citations": []},
    )
    respx.post("http://mock-api/api/v1/reports/generate").respond(
        200,
        json={"id": "r1", "status": "COMPLETED"},
    )

    with AnalystForgeClient(base_url="http://mock-api") as client:
        res = client.query_research("What is the valuation?", ticker="AAPL")
        assert res["answer"] == "Bullish"

        rep = client.generate_report(title="Apple Memo", ticker="AAPL")
        assert rep["id"] == "r1"


@respx.mock
def test_client_error_handling():
    respx.get("http://mock-api/api/v1/companies/NONEXIST").respond(
        404,
        json={"error": {"code": "not_found", "message": "Company not found"}},
    )

    with AnalystForgeClient(base_url="http://mock-api") as client:
        with pytest.raises(AnalystForgeError) as exc_info:
            client.get_company("NONEXIST")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "not_found"
