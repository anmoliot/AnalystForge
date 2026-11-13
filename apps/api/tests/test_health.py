from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_health_is_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "analystforge-api"
    assert body["version"] == "0.1.0"
    assert body["uptime_seconds"] >= 0


async def test_ready_checks_database_and_storage(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["storage"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "not_configured"


async def test_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "client-request-123456"})
    assert response.headers["x-request-id"] == "client-request-123456"


async def test_invalid_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "bad id"})
    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 32
    assert response.headers["x-request-id"] != "bad id"


async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == response.headers["x-request-id"]


async def test_method_not_allowed_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_metrics_endpoint_exposes_prometheus_text(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/meta")
    assert response.status_code == 200
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "analystforge_http_requests_total" in metrics.text
    assert 'route="/api/v1/meta"' in metrics.text


async def test_unmatched_requests_have_bounded_metric_label(client: httpx.AsyncClient) -> None:
    await client.get("/api/v1/does-not-exist")
    metrics = await client.get("/metrics")
    assert 'route="<unmatched>"' in metrics.text
    assert "does-not-exist" not in metrics.text


async def test_meta_reports_disclaimer_and_capabilities(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/meta")
    body = response.json()
    assert body["demo_mode"] is False
    assert "not investment advice" in body["disclaimer"].lower()
    assert body["capabilities"]["llm_provider"] == "none"
    assert body["capabilities"]["redis"] is False
    assert body["capabilities"]["market_data"] is False
