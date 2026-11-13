"""Provider health, data coverage and quality endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from analystforge.api.services.coverage import data_coverage
from analystforge.api.services.quality import run_quality_checks
from analystforge.api.services.runtime import provider_health

router = APIRouter(tags=["data"])


@router.get("/providers/health", summary="Latest provider status and failover history")
async def providers_health(request: Request) -> dict[str, Any]:
    registry = request.app.state.provider_registry
    async with request.app.state.db.session() as session:
        rows = await provider_health(session, registry)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "providers": rows,
    }


@router.get("/data/coverage", summary="Ingested data coverage by exchange and dataset")
async def coverage(request: Request) -> dict[str, Any]:
    async with request.app.state.db.session() as session:
        return await data_coverage(session)


@router.get("/data/quality", summary="On-demand data-quality report")
async def quality(request: Request) -> dict[str, Any]:
    async with request.app.state.db.session() as session:
        report = await run_quality_checks(session)
    return report.as_dict()
