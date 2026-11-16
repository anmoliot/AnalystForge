"""Live integration test suite for FRED and Groq APIs.

Runs only when explicitly invoked via `pytest -m live` with real keys present in `.env`.
Never logs, prints, or exposes API keys.
"""

from __future__ import annotations

from datetime import date, timedelta
import os
import pytest

from analystforge.api.config import get_settings
from analystforge.providers.llm import ChatMessage, OpenAICompatibleProvider
from analystforge.providers.macro.fred import FredProvider
from analystforge.providers.models import MacroSeriesSpec


@pytest.fixture
def settings():
    return get_settings()


@pytest.mark.live
@pytest.mark.network
@pytest.mark.asyncio
async def test_live_fred_api(settings) -> None:
    fred_key = settings.provider_key("fred")
    if not fred_key:
        pytest.skip("FRED_API_KEY not configured in .env; skipping live FRED test.")

    provider = FredProvider(
        user_agent=settings.sec_user_agent,
        api_key=fred_key,
        timeout_seconds=15.0,
    )
    try:
        # Check reachability
        reachable, err = await provider.check_reachability()
        assert reachable, f"FRED reachability failed: {err}"

        # Ingest sample series (10-Year Treasury Constant Maturity)
        end = date.today()
        start = end - timedelta(days=30)
        spec = MacroSeriesSpec(
            code="DGS10",
            title="10-Year Treasury Constant Maturity Rate",
            units="Percent",
            frequency="daily",
        )
        series = await provider.fetch_series(spec, start, end)
        assert series.spec.code == "DGS10"
        assert len(series.points) > 0
    finally:
        await provider.aclose()


@pytest.mark.live
@pytest.mark.network
@pytest.mark.asyncio
async def test_live_groq_llm_api(settings) -> None:
    llm_key = settings.provider_key("openai-compatible") or settings.provider_key("groq")
    if not llm_key:
        pytest.skip("LLM_API_KEY (Groq) not configured in .env; skipping live Groq test.")

    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=llm_key,
        model=settings.llm_model,
        fallback_model=settings.llm_fallback_model,
        max_input_tokens=settings.llm_max_input_tokens,
        requests_per_minute=settings.llm_requests_per_minute,
        timeout_seconds=20.0,
    )
    try:
        # Check reachability and dynamic model resolution
        reachable, err = await provider.check_reachability()
        assert reachable, f"Groq reachability failed: {err}"

        resolved = await provider.resolve_model()
        assert resolved, "Model resolution should return an active model"

        # Chat completion test
        messages = [
            ChatMessage(role="system", content="You are a concise financial assistant. Reply in one sentence."),
            ChatMessage(role="user", content="What is the definition of Free Cash Flow to Equity?"),
        ]
        resp = await provider.complete(messages, max_tokens=300)
        assert resp.content and len(resp.content) > 10
        assert resp.model

        # Streaming test
        stream_chunks: list[str] = []
        async for chunk in provider.stream(messages, max_tokens=150):
            stream_chunks.append(chunk)
        streamed_text = "".join(stream_chunks)
        assert len(streamed_text) > 0
    finally:
        await provider.aclose()
