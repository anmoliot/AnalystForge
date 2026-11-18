"""Tests for Grounded Research Assistant & RAG API (Phase 9)."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"analyst_{uuid.uuid4().hex[:6]}@hedgefund.com"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Research Analyst",
            "tenant_name": "Deep Research Partners",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_research_query_unauthenticated(client: AsyncClient):
    response = await client.post(
        "/api/v1/research/query",
        json={
            "query": "What are the latest risk factors and revenue trends?",
            "ticker": "AAPL",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "citations" in data
    assert isinstance(data["citations"], list)
    assert data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_research_sessions_lifecycle(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    # 1. Create a research session
    create_res = await client.post(
        "/api/v1/research/sessions",
        headers=auth_headers,
        json={"title": "NVIDIA FY2025 Deep Dive", "ticker": "NVDA"},
    )
    assert create_res.status_code == 200
    session_id = create_res.json()["id"]

    # 2. List sessions
    list_res = await client.get("/api/v1/research/sessions", headers=auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(s["id"] == session_id for s in items)

    # 3. Query with session_id to persist
    query_res = await client.post(
        "/api/v1/research/query",
        headers=auth_headers,
        json={
            "query": "What is the data center revenue growth?",
            "ticker": "NVDA",
            "session_id": session_id,
        },
    )
    assert query_res.status_code == 200
    assert query_res.json()["session_id"] == session_id

    # 4. Get session messages
    detail_res = await client.get(
        f"/api/v1/research/sessions/{session_id}",
        headers=auth_headers,
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert len(detail["messages"]) >= 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"
