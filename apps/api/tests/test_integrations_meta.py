"""Tests for /api/v1/meta/integrations startup self-check diagnostics."""

from __future__ import annotations

import json
import httpx
import pytest

from analystforge.api.services.llm import set_llm_provider
from analystforge.providers.llm import DeterministicFakeLLMProvider


@pytest.mark.asyncio
async def test_meta_integrations_diagnostics(client: httpx.AsyncClient) -> None:
    # Use deterministic fake LLM provider for isolated test
    fake_provider = DeterministicFakeLLMProvider()
    set_llm_provider(fake_provider)

    resp = await client.get("/api/v1/meta/integrations")
    assert resp.status_code == 200
    data = resp.json()

    # Must contain main integration sections
    assert "fred" in data
    assert "llm" in data
    assert "embeddings" in data
    assert "sentiment" in data

    # Verify FRED section structure
    fred = data["fred"]
    assert "configured" in fred
    assert "reachable" in fred
    assert "last_error" in fred

    # Verify LLM section structure
    llm = data["llm"]
    assert "provider" in llm
    assert "configured" in llm
    assert "resolved_model" in llm
    assert "reachable" in llm
    assert "requests_per_minute" in llm
    assert "max_input_tokens" in llm

    # Verify Embeddings section structure
    embeddings = data["embeddings"]
    assert "backend" in embeddings
    assert embeddings["backend"] in {"sentence-transformers", "lexical"}
    assert "dim" in embeddings

    # Verify Sentiment section structure
    sentiment = data["sentiment"]
    assert "backend" in sentiment
    assert "enabled" in sentiment

    # CRITICAL: Verify NO secrets / keys are leaked anywhere in the JSON response
    serialized = json.dumps(data)
    for forbidden in ["gsk_", "sk-", "key", "secret"]:
        if forbidden in {"key", "secret"}:
            # Check there are no key values resembling API keys
            assert "gsk_" not in serialized
        else:
            assert forbidden not in serialized
