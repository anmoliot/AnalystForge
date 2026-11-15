"""Valuation workbench endpoints: DCF engine, sensitivity, Monte Carlo, Excel export, and model versioning."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError, PermissionDeniedError
from analystforge.api.models.valuation import ValuationModel, ValuationVersion
from analystforge.api.services.valuation import (
    compute_monte_carlo,
    compute_sensitivity_grid,
    execute_dcf,
    generate_dcf_excel_workbook,
)

router = APIRouter(prefix="/valuation", tags=["valuation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DCFRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    base_revenue: float = Field(gt=0)
    revenue_growth: list[float] = Field(min_length=1)
    ebit_margin: list[float] = Field(min_length=1)
    tax_rate: float = Field(ge=0, le=1)
    wacc: float = Field(gt=0, le=1)
    terminal_growth: float = Field(ge=-0.1, le=0.1, default=0.025)
    shares_outstanding: float = Field(gt=0)
    depreciation_pct_revenue: float = Field(ge=0, le=1, default=0.04)
    capex_pct_revenue: float = Field(ge=0, le=1, default=0.05)
    nwc_pct_incremental_revenue: float = Field(ge=-1, le=1, default=0.10)
    net_debt: float = Field(default=0.0)
    mid_year_convention: bool = True
    terminal_method: str = "gordon_growth"
    exit_multiple: float | None = None


class SensitivityRequest(DCFRequest):
    wacc_steps: list[float] | None = None
    g_steps: list[float] | None = None


class SaveModelRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    model_type: str = "DCF"
    scenario: str = "base"
    assumptions: dict[str, Any]
    results: dict[str, Any]
    notes: str | None = None


class SaveVersionRequest(BaseModel):
    scenario: str = "base"
    assumptions: dict[str, Any]
    results: dict[str, Any]
    notes: str | None = None


class VersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    scenario: str
    assumptions: dict[str, Any]
    results: dict[str, Any]
    notes: str | None
    created_at: str

    model_config = {"from_attributes": True}


class ModelSummaryResponse(BaseModel):
    id: uuid.UUID
    ticker: str
    name: str
    model_type: str
    latest_version: int
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# DCF Calculation Endpoints
# ---------------------------------------------------------------------------


@router.post("/dcf", summary="Calculate DCF valuation and projected cash flows")
async def calculate_dcf(body: DCFRequest) -> dict[str, Any]:
    return execute_dcf(body.model_dump())


@router.post("/dcf/sensitivity", summary="2D sensitivity table for WACC vs Terminal Growth")
async def sensitivity_table(body: SensitivityRequest) -> dict[str, Any]:
    return compute_sensitivity_grid(
        body.model_dump(), wacc_steps=body.wacc_steps, g_steps=body.g_steps
    )


@router.post("/dcf/montecarlo", summary="Monte Carlo simulation on growth and margin drivers")
async def monte_carlo(
    body: DCFRequest,
    iterations: Annotated[int, Query(ge=100, le=5000)] = 1000,
) -> dict[str, Any]:
    return compute_monte_carlo(body.model_dump(), iterations=iterations)


@router.post("/dcf/export/excel", summary="Export DCF model as an Excel workbook with live formulas")
async def export_excel(body: DCFRequest) -> Response:
    params = body.model_dump()
    result = execute_dcf(params)
    file_bytes = generate_dcf_excel_workbook(params, result, company_name=body.ticker)

    filename = f"{body.ticker}_DCF_Valuation.xlsx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Saved Model & Version History CRUD
# ---------------------------------------------------------------------------


@router.post("/models", status_code=201, summary="Save valuation model")
async def save_model(
    body: SaveModelRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    model = ValuationModel(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        ticker=body.ticker.upper(),
        name=body.name,
        model_type=body.model_type,
    )
    session.add(model)
    await session.flush()

    version = ValuationVersion(
        model_id=model.id,
        version_number=1,
        scenario=body.scenario,
        assumptions=body.assumptions,
        results=body.results,
        notes=body.notes,
    )
    session.add(version)
    await session.commit()

    return {
        "model_id": str(model.id),
        "version_id": str(version.id),
        "version_number": 1,
        "ticker": model.ticker,
        "name": model.name,
    }


@router.get("/models", summary="List saved valuation models")
async def list_models(
    current_user: CurrentUser,
    session: SessionDep,
    ticker: str | None = None,
) -> list[ModelSummaryResponse]:
    query = select(ValuationModel).where(ValuationModel.tenant_id == current_user.tenant_id)
    if ticker:
        query = query.where(ValuationModel.ticker == ticker.upper())
    query = query.order_by(desc(ValuationModel.updated_at))

    res = await session.execute(query)
    models = res.scalars().all()

    items: list[ModelSummaryResponse] = []
    for m in models:
        latest_ver_stmt = (
            select(ValuationVersion.version_number)
            .where(ValuationVersion.model_id == m.id)
            .order_by(desc(ValuationVersion.version_number))
            .limit(1)
        )
        ver_res = await session.execute(latest_ver_stmt)
        ver_num = ver_res.scalar_one_or_none() or 1

        items.append(
            ModelSummaryResponse(
                id=m.id,
                ticker=m.ticker,
                name=m.name,
                model_type=m.model_type,
                latest_version=ver_num,
                created_at=m.created_at.isoformat(),
                updated_at=m.updated_at.isoformat(),
            )
        )

    return items


@router.get("/models/{model_id}", summary="Get model with version history")
async def get_model(
    model_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    model = await session.get(ValuationModel, model_id)
    if not model or model.tenant_id != current_user.tenant_id:
        raise NotFoundError("Valuation model not found.")

    v_stmt = (
        select(ValuationVersion)
        .where(ValuationVersion.model_id == model.id)
        .order_by(desc(ValuationVersion.version_number))
    )
    v_res = await session.execute(v_stmt)
    versions = v_res.scalars().all()

    return {
        "id": str(model.id),
        "ticker": model.ticker,
        "name": model.name,
        "model_type": model.model_type,
        "description": model.description,
        "created_at": model.created_at.isoformat(),
        "updated_at": model.updated_at.isoformat(),
        "versions": [
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "scenario": v.scenario,
                "assumptions": v.assumptions,
                "results": v.results,
                "notes": v.notes,
                "created_at": v.created_at.isoformat(),
            }
            for v in versions
        ],
    }


@router.post("/models/{model_id}/versions", status_code=201, summary="Save new version / scenario")
async def save_version(
    model_id: uuid.UUID,
    body: SaveVersionRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    model = await session.get(ValuationModel, model_id)
    if not model or model.tenant_id != current_user.tenant_id:
        raise NotFoundError("Valuation model not found.")

    latest_stmt = (
        select(ValuationVersion.version_number)
        .where(ValuationVersion.model_id == model_id)
        .order_by(desc(ValuationVersion.version_number))
        .limit(1)
    )
    latest_res = await session.execute(latest_stmt)
    latest_num = latest_res.scalar_one_or_none() or 0
    next_num = latest_num + 1

    version = ValuationVersion(
        model_id=model.id,
        version_number=next_num,
        scenario=body.scenario,
        assumptions=body.assumptions,
        results=body.results,
        notes=body.notes,
    )
    session.add(version)
    await session.commit()

    return {
        "id": str(version.id),
        "model_id": str(model.id),
        "version_number": next_num,
        "scenario": version.scenario,
    }


@router.delete("/models/{model_id}", status_code=204, summary="Delete valuation model")
async def delete_model(
    model_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    model = await session.get(ValuationModel, model_id)
    if not model or model.tenant_id != current_user.tenant_id:
        raise NotFoundError("Valuation model not found.")

    await session.delete(model)
    await session.commit()
