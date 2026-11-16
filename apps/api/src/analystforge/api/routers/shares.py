"""Expiring read-only share links API.

Allows analysts to generate time-limited read-only links for portfolios, screens,
backtests, or valuations that can be viewed publicly without authentication before expiry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.backtest import BacktestRun
from analystforge.api.models.collaboration import ShareLink
from analystforge.api.models.portfolio import Portfolio
from analystforge.api.models.screener import SavedScreen
from analystforge.api.models.valuation import ValuationModel

router = APIRouter(prefix="/shares", tags=["shares"])
public_share_router = APIRouter(prefix="/public/shares", tags=["public-shares"])


class CreateShareLinkRequest(BaseModel):
    resource_type: str = Field(pattern="^(portfolio|screen|backtest|valuation)$")
    resource_id: str = Field(min_length=1, max_length=128)
    expires_in_days: int = Field(default=7, ge=1, le=90)


@router.post("", status_code=201, summary="Generate an expiring read-only share link")
async def create_share_link(
    payload: CreateShareLinkRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    link = ShareLink(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        expires_at=expires_at,
        is_active=True,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)

    return {
        "id": str(link.id),
        "token": link.token,
        "resource_type": link.resource_type,
        "resource_id": link.resource_id,
        "expires_at": link.expires_at.isoformat(),
        "is_active": link.is_active,
        "share_url": f"/public/shares/{link.token}",
    }


@router.get("", summary="List tenant's share links")
async def list_share_links(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    stmt = (
        select(ShareLink)
        .where(ShareLink.tenant_id == current_user.tenant_id)
        .order_by(desc(ShareLink.created_at))
    )
    links = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    return [
        {
            "id": str(l.id),
            "token": l.token,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "expires_at": l.expires_at.isoformat(),
            "is_active": l.is_active,
            "is_expired": l.expires_at < now,
            "view_count": l.view_count,
            "share_url": f"/public/shares/{l.token}",
            "created_at": l.created_at.isoformat(),
        }
        for l in links
    ]


@router.delete("/{share_id}", status_code=204, summary="Revoke a share link")
async def revoke_share_link(
    share_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    link = await session.get(ShareLink, share_id)
    if not link or link.tenant_id != current_user.tenant_id:
        raise NotFoundError("Share link not found.")
    link.is_active = False
    await session.commit()


@public_share_router.get("/{token}", summary="Public unauthenticated read-only resource retrieval via share token")
async def view_shared_resource(
    token: str,
    session: SessionDep,
) -> dict[str, Any]:
    stmt = select(ShareLink).where(ShareLink.token == token)
    link = (await session.execute(stmt)).scalar_one_or_none()

    if not link or not link.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found or inactive.")

    now = datetime.now(timezone.utc)
    # Check expiry
    exp = link.expires_at if link.expires_at.tzinfo else link.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link has expired.",
        )

    # Increment view count
    link.view_count += 1
    await session.commit()

    # Load shared payload
    res_data: dict[str, Any] = {}
    if link.resource_type == "portfolio":
        try:
            p_uuid = uuid.UUID(link.resource_id)
            p = await session.get(Portfolio, p_uuid)
            if p:
                res_data = {"id": str(p.id), "name": p.name, "description": p.description, "base_currency": p.base_currency}
        except Exception:
            pass

    elif link.resource_type == "screen":
        try:
            s_uuid = uuid.UUID(link.resource_id)
            s = await session.get(SavedScreen, s_uuid)
            if s:
                res_data = {"id": str(s.id), "name": s.name, "description": s.description, "filters": s.filters}
        except Exception:
            pass

    elif link.resource_type == "backtest":
        try:
            b_uuid = uuid.UUID(link.resource_id)
            b = await session.get(BacktestRun, b_uuid)
            if b:
                res_data = {
                    "id": str(b.id),
                    "ticker": b.ticker,
                    "strategy_name": b.strategy_name,
                    "total_return": float(b.total_return),
                    "sharpe_ratio": float(b.sharpe_ratio) if b.sharpe_ratio else None,
                    "equity_curve": b.equity_curve,
                }
        except Exception:
            pass

    elif link.resource_type == "valuation":
        try:
            v_uuid = uuid.UUID(link.resource_id)
            v = await session.get(ValuationModel, v_uuid)
            if v:
                res_data = {"id": str(v.id), "name": v.name, "ticker": v.ticker, "model_type": v.model_type}
        except Exception:
            pass

    return {
        "resource_type": link.resource_type,
        "resource_id": link.resource_id,
        "expires_at": link.expires_at.isoformat(),
        "view_count": link.view_count,
        "data": res_data,
    }
