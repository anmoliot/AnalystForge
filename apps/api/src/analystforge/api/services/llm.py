"""LLM Provider factory and runtime lifecycle for the API."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from analystforge.api.config import Settings, get_settings
from analystforge.providers.llm import (
    AnthropicProvider,
    ChatMessage,
    DeterministicFakeLLMProvider,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    NoneLLMProvider,
    OpenAICompatibleProvider,
    ToolCall,
)

logger = structlog.get_logger("api.llm")

_LLM_PROVIDER_INSTANCE: LLMProvider | None = None


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider_type = settings.llm_provider.lower()
    api_key = settings.provider_key(settings.llm_provider) or settings.provider_key("openai-compatible") or settings.provider_key("groq")

    if provider_type == "none" or not api_key:
        return NoneLLMProvider()

    if provider_type in {"openai-compatible", "openai", "groq"}:
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=api_key,
            model=settings.llm_model,
            fallback_model=settings.llm_fallback_model,
            max_input_tokens=settings.llm_max_input_tokens,
            requests_per_minute=settings.llm_requests_per_minute,
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.sec_user_agent,
        )

    if provider_type == "anthropic":
        return AnthropicProvider(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022",
            timeout_seconds=settings.http_timeout_seconds,
            requests_per_minute=settings.llm_requests_per_minute,
        )

    logger.warning("llm.unknown_provider", provider=provider_type)
    return NoneLLMProvider()


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    global _LLM_PROVIDER_INSTANCE
    if _LLM_PROVIDER_INSTANCE is None:
        cfg = settings or get_settings()
        _LLM_PROVIDER_INSTANCE = create_llm_provider(cfg)
    return _LLM_PROVIDER_INSTANCE


def set_llm_provider(provider: LLMProvider) -> None:
    """Override LLM provider for tests."""
    global _LLM_PROVIDER_INSTANCE
    _LLM_PROVIDER_INSTANCE = provider
