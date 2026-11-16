"""Tests for LLM providers: OpenAI-compatible (Groq), Anthropic, None, and Fake."""

from __future__ import annotations

import json
import pytest
import respx
import httpx

from analystforge.providers.errors import ProviderNotConfiguredError
from analystforge.providers.llm import (
    ChatMessage,
    DeterministicFakeLLMProvider,
    LLMRateLimitError,
    NoneLLMProvider,
    OpenAICompatibleProvider,
    TokenBucket,
    ToolCall,
)


@pytest.mark.asyncio
async def test_none_llm_provider() -> None:
    provider = NoneLLMProvider()
    assert not provider.is_configured()
    reachable, err = await provider.check_reachability()
    assert not reachable
    assert "none" in err.lower()

    with pytest.raises(ProviderNotConfiguredError):
        await provider.complete([{"role": "user", "content": "hello"}])

    with pytest.raises(ProviderNotConfiguredError):
        async for _ in provider.stream([{"role": "user", "content": "hello"}]):
            pass


@pytest.mark.asyncio
async def test_deterministic_fake_llm_provider() -> None:
    provider = DeterministicFakeLLMProvider(canned_response="AAPL fair value is $220.")
    assert provider.is_configured()
    reachable, err = await provider.check_reachability()
    assert reachable
    assert err is None

    # Chat completion
    resp = await provider.complete([{"role": "user", "content": "Valuation of AAPL"}])
    assert resp.content == "AAPL fair value is $220."
    assert resp.model == "deterministic-fake-model-v1"

    # JSON structured completion
    json_resp = await provider.complete(
        [{"role": "user", "content": "Analyze AAPL"}],
        response_format={"type": "json_object"},
    )
    parsed = json.loads(json_resp.content)
    assert parsed["confidence"] == 0.95

    # Tool calling
    tool_resp = await provider.complete(
        [{"role": "user", "content": "Calculate DCF for AAPL"}],
        tools=[{"type": "function", "function": {"name": "calculate_dcf"}}],
    )
    assert len(tool_resp.tool_calls) == 1
    assert tool_resp.tool_calls[0].name == "calculate_dcf"

    # Streaming
    tokens: list[str] = []
    async for chunk in provider.stream([{"role": "user", "content": "Stream"}]):
        tokens.append(chunk)
    assert "".join(tokens).strip() == "AAPL fair value is $220."


@pytest.mark.asyncio
async def test_token_bucket_limiter() -> None:
    bucket = TokenBucket(rate_per_minute=60)  # 1 token/sec
    # Initial capacity should allow immediate acquire
    waited = await bucket.acquire(timeout=2.0)
    assert waited < 0.1

    # Emptying bucket and testing timeout
    bucket.tokens = 0.0
    with pytest.raises(LLMRateLimitError) as exc_info:
        await bucket.acquire(timeout=0.05)
    assert "rate limited" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_openai_compatible_model_resolution() -> None:
    base_url = "https://api.groq.com/openai/v1"
    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key="gsk_test_key",
        model="llama-3.3-70b-versatile",
        fallback_model="llama-3.1-8b-instant",
    )

    # 1. Primary model present
    respx.get(f"{base_url}/models").respond(
        200,
        json={"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "llama-3.1-8b-instant"}]},
    )
    resolved = await provider.resolve_model()
    assert resolved == "llama-3.3-70b-versatile"
    reachable, err = await provider.check_reachability()
    assert reachable
    assert err is None

    # 2. Primary model missing, fallback present
    respx.get(f"{base_url}/models").respond(
        200,
        json={"data": [{"id": "llama-3.1-8b-instant"}, {"id": "other-model"}]},
    )
    resolved_fb = await provider.resolve_model()
    assert resolved_fb == "llama-3.1-8b-instant"


@pytest.mark.asyncio
@respx.mock
async def test_openai_compatible_chat_and_tools() -> None:
    base_url = "https://api.groq.com/openai/v1"
    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key="gsk_test_key",
        model="llama-3.3-70b-versatile",
    )

    # Mock chat completion with tool call
    chat_response_payload = {
        "id": "chatcmpl-123",
        "model": "llama-3.3-70b-versatile",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Running DCF valuation model...",
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "quick_dcf",
                                "arguments": json.dumps({"ticker": "AAPL", "wacc": 0.085}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45},
    }
    respx.post(f"{base_url}/chat/completions").respond(200, json=chat_response_payload)

    resp = await provider.complete(
        [
            ChatMessage(role="system", content="You are a financial research assistant."),
            ChatMessage(role="user", content="Calculate DCF for AAPL"),
        ],
        tools=[{"type": "function", "function": {"name": "quick_dcf"}}],
    )
    assert resp.content == "Running DCF valuation model..."
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "quick_dcf"
    assert resp.tool_calls[0].arguments["ticker"] == "AAPL"
    assert resp.prompt_tokens == 120
    assert resp.completion_tokens == 45


@pytest.mark.asyncio
@respx.mock
async def test_openai_compatible_streaming() -> None:
    base_url = "https://api.groq.com/openai/v1"
    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key="gsk_test_key",
        model="llama-3.3-70b-versatile",
    )

    sse_data = (
        'data: {"choices": [{"delta": {"content": "AAPL "}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "revenue "}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "growth is 10%."}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(f"{base_url}/chat/completions").respond(
        200,
        content=sse_data.encode("utf-8"),
        headers={"Content-Type": "text/event-stream"},
    )

    chunks: list[str] = []
    async for chunk in provider.stream([{"role": "user", "content": "stream test"}]):
        chunks.append(chunk)

    assert "".join(chunks) == "AAPL revenue growth is 10%."


@pytest.mark.asyncio
@respx.mock
async def test_openai_compatible_rate_limit_and_retry() -> None:
    base_url = "https://api.groq.com/openai/v1"
    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key="gsk_test_key",
        max_retries=2,
    )

    # 429 with Retry-After header
    respx.post(f"{base_url}/chat/completions").respond(
        429,
        headers={"Retry-After": "1"},
        json={"error": {"message": "Rate limit exceeded"}},
    )

    with pytest.raises(LLMRateLimitError) as exc_info:
        await provider.complete([{"role": "user", "content": "test"}])
    assert "rate limited" in str(exc_info.value).lower()
    assert exc_info.value.retry_after >= 1.0


def test_context_trimming_preserves_system_prompt() -> None:
    provider = OpenAICompatibleProvider(
        max_input_tokens=100,  # ~400 characters max
    )
    system_msg = {"role": "system", "content": "SYSTEM DIRECTIVE: Always cite sources."}
    long_passage = "A" * 600
    user_query = {"role": "user", "content": "What is the valuation?"}

    trimmed = provider._trim_messages([
        system_msg,
        {"role": "user", "content": long_passage},
        user_query,
    ])

    # System message must be preserved
    assert trimmed[0]["role"] == "system"
    assert trimmed[0]["content"] == "SYSTEM DIRECTIVE: Always cite sources."
    # Total characters should not exceed approx max_input_tokens * 4
    total_chars = sum(len(m.get("content", "")) for m in trimmed)
    assert total_chars <= 500
