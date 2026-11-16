"""Watchlists API for managing multi-asset monitoring lists."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.collaboration import Watchlist, WatchlistItem
from analystforge.api.models.market import Instrument, PriceBar

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


class CreateWatchlistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    is_default: bool = False


class AddWatchlistItemRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    target_price: float | None = None
    notes: str | None = None


@router.post("", status_code=201, summary="Create a new watchlist")
async def create_watchlist(
    payload: CreateWatchlistRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    wl = Watchlist(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        is_default=payload.is_default,
    )
    session.add(wl)
    await session.commit()
    await session.refresh(wl)
    return {
        "id": str(wl.id),
        "name": wl.name,
        "description": wl.description,
        "is_default": wl.is_default,
        "created_at": wl.created_at.isoformat(),
        "items_count": 0,
    }


@router.get("", summary="List user's watchlists")
async def list_watchlists(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    stmt = (
        select(Watchlist)
        .options(selectinload(Watchlist.items))
        .where(Watchlist.tenant_id == current_user.tenant_id)
        .order_by(desc(Watchlist.created_at))
    )
    lists = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(w.id),
            "name": w.name,
            "description": w.description,
            "is_default": w.is_default,
            "items_count": len(w.items),
            "created_at": w.created_at.isoformat(),
        }
        for w in lists
    ]


@router.get("/{watchlist_id}", summary="Get watchlist detail with current live prices")
async def get_watchlist(
    watchlist_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    stmt = (
        select(Watchlist)
        .options(selectinload(Watchlist.items))
        .where(Watchlist.id == watchlist_id, Watchlist.tenant_id == current_user.tenant_id)
    )
    wl = (await session.execute(stmt)).scalar_one_or_none()
    if not wl:
        raise NotFoundError("Watchlist not found.")

    items_with_prices: list[dict[str, Any]] = []
    for it in wl.items:
        # Retrieve latest price
        inst_stmt = select(Instrument).where(Instrument.ticker == it.ticker)
        inst = (await session.execute(inst_stmt)).scalar_one_or_none()
        price = None
        as_of = None
        if inst:
            bar_stmt = (
                select(PriceBar)
                .where(PriceBar.instrument_id == inst.id, PriceBar.interval == "1d")
                .order_by(desc(PriceBar.ts))
                .limit(1)
            )
            bar = (await session.execute(bar_stmt)).scalar_one_or_none()
            if bar:
                price = float(bar.close)
                as_of = bar.ts.date().isoformat()

        items_with_prices.append({
            "id": str(it.id),
            "ticker": it.ticker,
            "name": inst.name if inst else it.ticker,
            "current_price": price,
            "target_price": float(it.target_price) if it.target_price is not None else None,
            "notes": it.notes,
            "as_of": as_of,
            "created_at": it.created_at.isoformat(),
        })

    return {
        "id": str(wl.id),
        "name": wl.name,
        "description": wl.description,
        "is_default": wl.is_default,
        "items": items_with_prices,
        "created_at": wl.created_at.isoformat(),
    }


@router.post("/{watchlist_id}/items", status_code=201, summary="Add ticker to watchlist")
async def add_watchlist_item(
    watchlist_id: uuid.UUID,
    payload: AddWatchlistItemRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    wl = await session.get(Watchlist, watchlist_id)
    if not wl or wl.tenant_id != current_user.tenant_id:
        raise NotFoundError("Watchlist not found.")

    ticker_clean = payload.ticker.upper()
    item = WatchlistItem(
        watchlist_id=wl.id,
        ticker=ticker_clean,
        target_price=Decimal(str(payload.target_price)) if payload.target_price is not None else None,
        notes=payload.notes,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    return {
        "id": str(item.id),
        "watchlist_id": str(wl.id),
        "ticker": item.ticker,
        "target_price": float(item.target_price) if item.target_price is not None else None,
        "notes": item.notes,
        "created_at": item.created_at.isoformat(),
    }


@router.delete("/{watchlist_id}/items/{item_id}", status_code=204, summary="Remove ticker from watchlist")
async def delete_watchlist_item(
    watchlist_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    wl = await session.get(Watchlist, watchlist_id)
    if not wl or wl.tenant_id != current_user.tenant_id:
        raise NotFoundError("Watchlist not found.")

    item = await session.get(WatchlistItem, item_id)
    if not item or item.watchlist_id != wl.id:
        raise NotFoundError("Watchlist item not found.")

    await session.delete(item)
    await session.commit()


@router.delete("/{watchlist_id}", status_code=204, summary="Delete watchlist")
async def delete_watchlist(
    watchlist_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    wl = await session.get(Watchlist, watchlist_id)
    if not wl or wl.tenant_id != current_user.tenant_id:
        raise NotFoundError("Watchlist not found.")

    await session.delete(wl)
    await session.commit()
