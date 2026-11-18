"""Valuation workbench endpoints: DCF, FCFE, DDM, Residual Income, Comps, SOTP, Precedents, WACC builder, and Football Field."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.valuation import ValuationModel, ValuationVersion
from analystforge.api.services.valuation import (
    compute_monte_carlo,
    compute_sensitivity_grid,
    execute_comps,
    execute_dcf,
    execute_ddm,
    execute_fcfe,
    execute_football_field,
    execute_precedents,
    execute_residual_income,
    execute_sotp,
    execute_wacc_builder,
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


class FCFERequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    base_net_income: float = Field(gt=0)
    net_income_growth: list[float] = Field(min_length=1)
    cost_of_equity: float = Field(gt=0, le=1)
    terminal_growth: float = Field(ge=-0.1, le=0.1, default=0.025)
    shares_outstanding: float = Field(gt=0)
    depreciation_pct_ni: float = Field(ge=0, default=0.10)
    capex_pct_ni: float = Field(ge=0, default=0.15)
    nwc_pct_ni: float = Field(default=0.05)
    net_borrowing_pct_ni: float = Field(default=0.05)
    terminal_method: str = "gordon_growth"
    exit_multiple: float | None = None
    mid_year_convention: bool = False


class DDMRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    model_type: str = "gordon"  # "gordon" or "multi_stage"
    cost_of_equity: float = Field(gt=0, le=1)
    # Gordon parameters
    dividend_t0: float | None = Field(default=None, gt=0)
    growth_rate: float | None = Field(default=None, ge=-0.1, le=0.1)
    # Multi-stage parameters
    base_dividend: float | None = Field(default=None, gt=0)
    stage1_growth: list[float] | None = None
    terminal_growth: float | None = Field(default=None, ge=-0.1, le=0.1)


class ResidualIncomeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    base_book_value: float = Field(gt=0)
    forecast_net_income: list[float] = Field(min_length=1)
    cost_of_equity: float = Field(gt=0, le=1)
    shares_outstanding: float = Field(gt=0)
    dividend_payout_ratio: float = Field(ge=0, le=1, default=0.0)
    terminal_method: str = "zero_growth"
    terminal_growth: float = Field(default=0.0)
    persistence_factor: float = Field(ge=0, le=1, default=1.0)


class CompsRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    peer_multiples: list[float] = Field(min_length=1)
    target_metric: float = Field(gt=0)
    shares_outstanding: float = Field(gt=0)
    net_debt: float = Field(default=0.0)
    is_equity_multiple: bool = False  # True for P/E or P/B, False for EV/EBITDA


class SOTPSegmentInput(BaseModel):
    name: str
    metric_name: str
    metric_value: float = Field(gt=0)
    multiple: float = Field(gt=0)
    ownership_pct: float = Field(gt=0, le=1, default=1.0)


class SOTPRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    segments: list[SOTPSegmentInput] = Field(min_length=1)
    shares_outstanding: float = Field(gt=0)
    net_debt: float = Field(default=0.0)
    non_controlling_interest: float = Field(default=0.0)
    investments_associates: float = Field(default=0.0)
    corporate_overhead_pv: float = Field(default=0.0)


class PrecedentDealInput(BaseModel):
    target: str
    announced_date: str = ""
    deal_value: float = Field(gt=0)
    target_metric: float = Field(gt=0)


class PrecedentsRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    deals: list[PrecedentDealInput] = Field(min_length=1)
    target_metric: float = Field(gt=0)
    shares_outstanding: float = Field(gt=0)
    net_debt: float = Field(default=0.0)


class WACCBuilderRequest(BaseModel):
    raw_beta: float = Field(default=1.0)
    apply_blume: bool = True
    risk_free_rate: float | None = None  # None queries live FRED DGS10
    equity_risk_premium: float = Field(default=0.055)
    pre_tax_cost_of_debt: float = Field(default=0.055)
    tax_rate: float = Field(ge=0, le=1, default=0.21)
    market_value_equity: float = Field(gt=0, default=1000000.0)
    market_value_debt: float = Field(ge=0, default=250000.0)


class ValuationRangeInput(BaseModel):
    method_id: str
    label: str
    category: str = "Intrinsic"
    low: float = Field(gt=0)
    base: float = Field(gt=0)
    high: float = Field(gt=0)
    notes: str | None = None


class FootballFieldRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    current_share_price: float | None = None
    ranges: list[ValuationRangeInput] = Field(min_length=1)


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
# Calculation Endpoints
# ---------------------------------------------------------------------------


@router.post("/dcf", summary="Calculate DCF (FCFF) valuation and projected cash flows")
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
    seed: Annotated[int, Query()] = 42,
) -> dict[str, Any]:
    return compute_monte_carlo(body.model_dump(), iterations=iterations, seed=seed)


@router.post(
    "/dcf/export/excel", summary="Export DCF model as an Excel workbook with live formulas"
)
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


@router.post("/fcfe", summary="Calculate Free Cash Flow to Equity (FCFE) model")
async def calculate_fcfe(body: FCFERequest) -> dict[str, Any]:
    return execute_fcfe(body.model_dump())


@router.post("/ddm", summary="Calculate Dividend Discount Model (single-stage or multi-stage)")
async def calculate_ddm(body: DDMRequest) -> dict[str, Any]:
    return execute_ddm(body.model_dump())


@router.post(
    "/residual-income", summary="Calculate Residual Income (Edwards-Bell-Ohlson) valuation"
)
async def calculate_residual_income(body: ResidualIncomeRequest) -> dict[str, Any]:
    return execute_residual_income(body.model_dump())


@router.post(
    "/comps", summary="Calculate Comparable Companies multiple distribution and valuation ranges"
)
async def calculate_comps(body: CompsRequest) -> dict[str, Any]:
    return execute_comps(body.model_dump())


@router.post("/sotp", summary="Calculate Sum of the Parts (SOTP) conglomerate valuation")
async def calculate_sotp(body: SOTPRequest) -> dict[str, Any]:
    return execute_sotp(body.model_dump())


@router.post(
    "/precedents", summary="Calculate Precedent Transactions M&A multiple valuation ranges"
)
async def calculate_precedents(body: PrecedentsRequest) -> dict[str, Any]:
    return execute_precedents(body.model_dump())


@router.post(
    "/wacc-builder", summary="Derive WACC with CAPM, Blume adjustment, and FRED risk-free rate"
)
async def derive_wacc(body: WACCBuilderRequest, session: SessionDep) -> dict[str, Any]:
    return await execute_wacc_builder(session, body.model_dump())


@router.post(
    "/football-field", summary="Consolidate multiple valuation ranges into a Football Field summary"
)
async def calculate_football_field(body: FootballFieldRequest) -> dict[str, Any]:
    return execute_football_field(body.model_dump())


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
