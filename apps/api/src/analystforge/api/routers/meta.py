"""Service metadata and capability discovery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["meta"])

DISCLAIMER = (
    "AnalystForge is a research and analysis tool, not investment advice. "
    "Market data may be delayed, incomplete or subject to provider terms. "
    "Always verify figures against primary sources before making decisions."
)


@router.get("/meta", summary="Service metadata and data capabilities")
async def meta(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    providers: dict[str, str] = getattr(request.app.state, "providers", None) or {}
    return {
        "name": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "api_version": "v1",
        "docs_url": "/docs",
        "disclaimer": DISCLAIMER,
        "capabilities": {
            "market_data": bool(providers.get("market_data")),
            "fundamentals": bool(providers.get("fundamentals")),
            "macro": bool(providers.get("macro")),
            "news": bool(providers.get("news")),
            "llm_provider": settings.llm_provider
            if settings.provider_key(settings.llm_provider)
            else "none",
            "local_sentiment": settings.finbert_enabled,
            "redis": bool(settings.redis_url),
        },
    }
