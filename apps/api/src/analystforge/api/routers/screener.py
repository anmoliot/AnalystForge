"""Screener API for multi-metric equity filtering, condition groups, saved screens, and exports."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import Float, and_, desc, func, select

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.market import Exchange, Instrument, PriceBar
from analystforge.api.models.research import FundamentalFact
from analystforge.api.models.screener import SavedScreen

router = APIRouter(prefix="/screener", tags=["screener"])


class ScreenerRule(BaseModel):
    field: str  # "price", "market_cap", "sector", "exchange", "pe_ratio", "roe", "volume"
    op: str = ">="  # ">=", "<=", "==", "!=", "contains", "in"
    value: Any


class ScreenerGroup(BaseModel):
    combinator: Literal["AND", "OR"] = "AND"
    rules: list[ScreenerRule] = Field(default_factory=list)
    groups: list[ScreenerGroup] = Field(default_factory=list)


class ScreenFilterRequest(BaseModel):
    exchange_code: str | None = None
    sector: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    min_pe: float | None = None
    max_pe: float | None = None
    min_roe: float | None = None
    search: str | None = None
    sort_by: str = "ticker"
    sort_dir: str = "asc"
    group: ScreenerGroup | None = None


class SaveScreenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = None  # daily, weekly, None
    notify_email: str | None = None


class ScheduleScreenRequest(BaseModel):
    schedule: str | None = Field(default="daily")  # daily, weekly, None
    notify_email: str | None = None


def _evaluate_rule_match(item: dict[str, Any], rule: ScreenerRule) -> bool:
    val = item.get(rule.field)
    target = rule.value
    if val is None:
        return False

    try:
        if rule.op in (">=", "gte"):
            return float(val) >= float(target)
        elif rule.op in ("<=", "lte"):
            return float(val) <= float(target)
        elif rule.op in (">", "gt"):
            return float(val) > float(target)
        elif rule.op in ("<", "lt"):
            return float(val) < float(target)
        elif rule.op in ("==", "eq"):
            return str(val).upper() == str(target).upper()
        elif rule.op in ("!=", "neq"):
            return str(val).upper() != str(target).upper()
        elif rule.op in ("contains", "ilike"):
            return str(target).upper() in str(val).upper()
        elif rule.op == "in":
            if isinstance(target, (list, tuple, set)):
                return str(val).upper() in [str(t).upper() for t in target]
            return str(val).upper() == str(target).upper()
    except (ValueError, TypeError):
        return False
    return False


def _evaluate_group_match(item: dict[str, Any], group: ScreenerGroup) -> bool:
    if not group.rules and not group.groups:
        return True

    results: list[bool] = []
    for r in group.rules:
        results.append(_evaluate_rule_match(item, r))

    for g in group.groups:
        results.append(_evaluate_group_match(item, g))

    if not results:
        return True

    if group.combinator == "AND":
        return all(results)
    else:  # OR
        return any(results)


async def _execute_screener_query(
    session: SessionDep,
    payload: ScreenFilterRequest,
) -> list[dict[str, Any]]:
    """Query universe instruments, fetch latest real prices and fundamentals, and apply filters."""
    latest_day = (
        select(func.max(PriceBar.ts))
        .where(PriceBar.instrument_id == Instrument.id, PriceBar.interval == "1d")
        .correlate(Instrument)
        .scalar_subquery()
    )
    concepts = ("CommonStockSharesOutstanding", "NetIncomeLoss", "StockholdersEquity")
    latest_facts = [
        select(FundamentalFact.value.cast(Float))
        .where(FundamentalFact.instrument_id == Instrument.id, FundamentalFact.concept == concept)
        .order_by(
            FundamentalFact.period_end.desc(),
            FundamentalFact.filed.desc(),
            FundamentalFact.id.desc(),
        )
        .limit(1)
        .correlate(Instrument)
        .scalar_subquery()
        for concept in concepts
    ]
    stmt = (
        select(Instrument, Exchange.code, PriceBar, *latest_facts)
        .select_from(Instrument)
        .join(Exchange, Instrument.exchange_code == Exchange.code)
        .join(
            PriceBar,
            and_(
                PriceBar.instrument_id == Instrument.id,
                PriceBar.interval == "1d",
                PriceBar.ts == latest_day,
            ),
        )
        .where(Instrument.is_active.is_(True))
    )

    if payload.exchange_code:
        stmt = stmt.where(Exchange.code == payload.exchange_code.upper())
    if payload.sector:
        stmt = stmt.where(Instrument.sector == payload.sector)
    if payload.search:
        term = f"%{payload.search.upper()}%"
        stmt = stmt.where(Instrument.ticker.ilike(term) | Instrument.name.ilike(term))

    inst_rows = (await session.execute(stmt)).all()
    results: list[dict[str, Any]] = []

    for inst, exch_code, latest_bar, shares_out, net_income, stockholders_equity in inst_rows:
        price = float(latest_bar.close)
        volume = float(latest_bar.volume) if latest_bar.volume is not None else None
        mkt_cap = price * shares_out if shares_out is not None else None

        pe_ratio: float | None = None
        if mkt_cap is not None and net_income and net_income > 0:
            pe_ratio = round(mkt_cap / net_income, 2)

        roe_pct: float | None = None
        if net_income and stockholders_equity and stockholders_equity > 0:
            roe_pct = round(net_income / stockholders_equity, 4)

        # Standard field filters
        if payload.min_price is not None and price < payload.min_price:
            continue
        if payload.max_price is not None and price > payload.max_price:
            continue
        if payload.min_market_cap is not None and (
            mkt_cap is None or mkt_cap < payload.min_market_cap
        ):
            continue
        if payload.max_market_cap is not None and (
            mkt_cap is None or mkt_cap > payload.max_market_cap
        ):
            continue
        if payload.min_pe is not None and (pe_ratio is None or pe_ratio < payload.min_pe):
            continue
        if payload.max_pe is not None and (pe_ratio is None or pe_ratio > payload.max_pe):
            continue
        if payload.min_roe is not None and (roe_pct is None or roe_pct < payload.min_roe):
            continue

        item = {
            "id": str(inst.id),
            "ticker": inst.ticker,
            "name": inst.name,
            "exchange": exch_code,
            "currency": inst.currency,
            "sector": inst.sector,
            "industry": inst.industry,
            "price": price,
            "volume": volume,
            "market_cap": mkt_cap,
            "pe_ratio": pe_ratio,
            "roe": roe_pct,
            "as_of": latest_bar.ts.date().isoformat(),
        }

        # AND/OR rule group evaluation
        if payload.group is not None and not _evaluate_group_match(item, payload.group):
            continue

        results.append(item)

    reverse = payload.sort_dir.lower() == "desc"
    key = (
        payload.sort_by
        if payload.sort_by in ["ticker", "price", "market_cap", "pe_ratio", "roe", "volume"]
        else "ticker"
    )
    results.sort(key=lambda x: (x.get(key) is None, x.get(key)), reverse=reverse)

    return results


@router.post("", summary="Screen universe on price, valuation multiples and fundamentals")
@router.post("/run", summary="Screen universe on price, valuation multiples and fundamentals")
async def run_screen(
    payload: ScreenFilterRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> Any:
    return await _execute_screener_query(session, payload)


@router.get("/export", summary="Export screened universe results as CSV or JSON")
async def export_screen_results(
    current_user: CurrentUser,
    session: SessionDep,
    format: Literal["csv", "json"] = "csv",
    exchange_code: str | None = None,
    sector: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_market_cap: float | None = None,
    max_market_cap: float | None = None,
    max_pe: float | None = None,
    min_roe: float | None = None,
) -> Response:
    req = ScreenFilterRequest(
        exchange_code=exchange_code,
        sector=sector,
        min_price=min_price,
        max_price=max_price,
        min_market_cap=min_market_cap,
        max_market_cap=max_market_cap,
        max_pe=max_pe,
        min_roe=min_roe,
    )
    items = await _execute_screener_query(session, req)

    if format == "json":
        import json

        return Response(
            content=json.dumps(items, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="screener_export.json"'},
        )

    # CSV output
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Ticker",
            "Company Name",
            "Exchange",
            "Sector",
            "Industry",
            "Price",
            "Market Cap",
            "P/E Ratio",
            "ROE",
            "Volume",
            "As-Of Date",
        ]
    )
    for it in items:
        writer.writerow(
            [
                it["ticker"],
                it["name"],
                it["exchange"],
                it.get("sector") or "",
                it.get("industry") or "",
                f"{it['price']:.2f}",
                f"{it['market_cap']:.0f}" if it["market_cap"] is not None else "",
                f"{it['pe_ratio']:.2f}" if it["pe_ratio"] is not None else "",
                f"{it['roe']:.4f}" if it["roe"] is not None else "",
                f"{it['volume']:.0f}" if it["volume"] is not None else "",
                it["as_of"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="screener_export.csv"'},
    )


@router.get("/saved", summary="List saved screen presets")
async def list_saved_screens(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    stmt = (
        select(SavedScreen)
        .where(SavedScreen.tenant_id == current_user.tenant_id)
        .order_by(desc(SavedScreen.created_at))
    )
    screens = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "filters": s.filters,
            "schedule": s.schedule,
            "notify_email": s.notify_email,
            "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in screens
    ]


@router.post("/saved", status_code=201, summary="Save screen preset")
async def save_screen(
    payload: SaveScreenRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    screen = SavedScreen(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        filters=payload.filters,
        schedule=payload.schedule,
        notify_email=payload.notify_email,
    )
    session.add(screen)
    await session.commit()
    await session.refresh(screen)
    return {
        "id": str(screen.id),
        "name": screen.name,
        "description": screen.description,
        "filters": screen.filters,
        "schedule": screen.schedule,
        "notify_email": screen.notify_email,
        "created_at": screen.created_at.isoformat(),
    }


@router.post("/saved/{screen_id}/run", summary="Run a saved screen preset")
async def run_saved_screen(
    screen_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    screen = await session.get(SavedScreen, screen_id)
    if not screen or screen.tenant_id != current_user.tenant_id:
        raise NotFoundError("Saved screen not found.")

    filters = screen.filters or {}
    req = ScreenFilterRequest(**filters)
    return await _execute_screener_query(session, req)


@router.post(
    "/saved/{screen_id}/schedule",
    summary="Configure automated schedule and email alert for saved screen",
)
async def schedule_saved_screen(
    screen_id: uuid.UUID,
    payload: ScheduleScreenRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    screen = await session.get(SavedScreen, screen_id)
    if not screen or screen.tenant_id != current_user.tenant_id:
        raise NotFoundError("Saved screen not found.")

    screen.schedule = payload.schedule
    screen.notify_email = payload.notify_email
    await session.commit()

    return {
        "id": str(screen.id),
        "name": screen.name,
        "schedule": screen.schedule,
        "notify_email": screen.notify_email,
        "message": f"Screen scheduled with frequency '{screen.schedule}'",
    }


@router.delete("/saved/{screen_id}", status_code=204, summary="Delete saved screen preset")
async def delete_saved_screen(
    screen_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    screen = await session.get(SavedScreen, screen_id)
    if not screen or screen.tenant_id != current_user.tenant_id:
        raise NotFoundError("Saved screen not found.")
    await session.delete(screen)
    await session.commit()
