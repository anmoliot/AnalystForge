"""Alert rules and notification events API (Phase 8)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.screener import AlertEvent, AlertRule

router = APIRouter(prefix="/alerts", tags=["alerts"])


class CreateAlertRuleRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    rule_type: str = Field(pattern="^(PRICE_ABOVE|PRICE_BELOW|PE_ABOVE|PE_BELOW)$")
    target_value: float = Field(gt=0)


@router.post("/rules", status_code=201, summary="Create a price or ratio alert rule")
async def create_alert_rule(
    payload: CreateAlertRuleRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict[str, Any]:
    rule = AlertRule(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        ticker=payload.ticker.upper(),
        rule_type=payload.rule_type,
        target_value=Decimal(str(payload.target_value)),
        is_active=True,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)

    return {
        "id": str(rule.id),
        "ticker": rule.ticker,
        "rule_type": rule.rule_type,
        "target_value": float(rule.target_value),
        "is_active": rule.is_active,
        "created_at": rule.created_at.isoformat(),
    }


@router.get("/rules", summary="List active alert rules")
async def list_alert_rules(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[dict[str, Any]]:
    stmt = (
        select(AlertRule)
        .where(AlertRule.tenant_id == current_user.tenant_id)
        .order_by(desc(AlertRule.created_at))
    )
    rules = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "ticker": r.ticker,
            "rule_type": r.rule_type,
            "target_value": float(r.target_value),
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat(),
        }
        for r in rules
    ]


@router.delete("/rules/{rule_id}", status_code=204, summary="Delete an alert rule")
async def delete_alert_rule(
    rule_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    rule = await session.get(AlertRule, rule_id)
    if not rule or rule.tenant_id != current_user.tenant_id:
        raise NotFoundError("Alert rule not found.")
    await session.delete(rule)
    await session.commit()


@router.get("/events", summary="List triggered alert notification events")
async def list_alert_events(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    stmt = (
        select(AlertEvent)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        .where(AlertRule.tenant_id == current_user.tenant_id)
        .order_by(desc(AlertEvent.triggered_at))
        .limit(limit)
    )
    events = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(e.id),
            "rule_id": str(e.rule_id),
            "ticker": e.ticker,
            "message": e.message,
            "triggered_value": float(e.triggered_value),
            "triggered_at": e.triggered_at.isoformat(),
        }
        for e in events
    ]
