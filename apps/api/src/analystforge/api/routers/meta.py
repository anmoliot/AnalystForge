"""Service metadata and capability discovery."""

from __future__ import annotations

import importlib.util
from typing import Any

from fastapi import APIRouter, Request

from analystforge.api.services.llm import get_llm_provider
from analystforge.providers.macro.fred import FredProvider

router = APIRouter(tags=["meta"])

DISCLAIMER = (
    "AnalystForge is a research and analysis tool, not investment advice. "
    "Market data may be delayed, incomplete or subject to provider terms. "
    "Always verify figures against primary sources before making decisions."
)


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


@router.get("/meta", summary="Service metadata and data capabilities")
async def meta(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    registry = getattr(request.app.state, "provider_registry", None)
    providers: dict[str, str | None] = registry.primary_map() if registry else {}
    return {
        "name": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "api_version": "v1",
        "docs_url": "/docs",
        "disclaimer": DISCLAIMER,
        "capabilities": {
            "market_data": bool(providers.get("prices")),
            "fundamentals": bool(providers.get("fundamentals")),
            "macro": bool(providers.get("macro")),
            "fx": bool(providers.get("fx")),
            "news": bool(providers.get("news")),
            "primary_providers": providers,
            "llm_provider": settings.llm_provider
            if settings.provider_key(settings.llm_provider)
            else "none",
            "local_sentiment": settings.finbert_enabled,
            "redis": bool(settings.redis_url),
        },
    }


@router.get("/meta/integrations", summary="Integration status and self-check diagnostics")
async def integrations(request: Request) -> dict[str, Any]:
    """Diagnostic self-check without revealing secret keys."""
    settings = request.app.state.settings
    registry = getattr(request.app.state, "provider_registry", None)

    # 1. FRED check
    fred_provider: FredProvider | None = None
    if registry:
        macro_router = registry.routers.get("macro")
        if macro_router:
            for p in macro_router.providers:
                if isinstance(p, FredProvider):
                    fred_provider = p
                    break

    if fred_provider is None:
        fred_key = settings.provider_key("fred")
        fred_provider = FredProvider(
            user_agent=settings.sec_user_agent,
            api_key=fred_key,
            timeout_seconds=settings.http_timeout_seconds,
        )

    fred_reachable, fred_error = await fred_provider.check_reachability()

    # 2. LLM check
    llm_provider = get_llm_provider(settings)
    llm_reachable, llm_error = await llm_provider.check_reachability()
    resolved_model = await llm_provider.resolve_model()

    # 3. Embedding and Sentiment backends
    has_sentence_transformers = _has_module("sentence_transformers")
    has_transformers = _has_module("transformers")

    embedding_backend = "sentence-transformers" if has_sentence_transformers else "lexical"
    sentiment_backend = (
        settings.finbert_model if (settings.finbert_enabled and has_transformers) else "lexical"
    )

    return {
        "fred": {
            "configured": bool(settings.provider_key("fred")),
            "reachable": fred_reachable,
            "last_error": fred_error,
        },
        "llm": {
            "provider": settings.llm_provider,
            "configured": llm_provider.is_configured(),
            "base_url": settings.llm_base_url
            if settings.llm_provider in {"openai-compatible", "openai", "groq"}
            else None,
            "configured_model": settings.llm_model,
            "fallback_model": settings.llm_fallback_model,
            "resolved_model": resolved_model,
            "reachable": llm_reachable,
            "last_error": llm_error,
            "requests_per_minute": settings.llm_requests_per_minute,
            "max_input_tokens": settings.llm_max_input_tokens,
        },
        "embeddings": {
            "backend": embedding_backend,
            "model": settings.embedding_model,
            "dim": settings.embedding_dim,
            "is_fallback": not has_sentence_transformers,
        },
        "sentiment": {
            "backend": sentiment_backend,
            "enabled": settings.finbert_enabled,
            "is_fallback": not (settings.finbert_enabled and has_transformers),
        },
    }
