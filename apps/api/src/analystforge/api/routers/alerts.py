"""Alert rules, real-time evaluation, and delivery notification events API."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from analystforge.api.deps import CurrentUser, SessionDep
from analystforge.api.errors import NotFoundError
from analystforge.api.models.screener import AlertDelivery, AlertEvent, AlertRule
from analystforge.api.services.alerts import evaluate_alert_rules

router = APIRouter(prefix="/alerts", tags=["alerts"])


class CreateAlertRuleRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    rule_type: str = Field(pattern="^(PRICE_ABOVE|PRICE_BELOW|PE_ABOVE|PE_BELOW)$")
    target_value: float = Field(gt=0)
    notification_channels: list[str] = Field(default_factory=lambda: ["in_app"])
    email_recipient: str | None = None
    webhook_url: str | None = None


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
        notification_channels=payload.notification_channels,
        email_recipient=payload.email_recipient,
        webhook_url=payload.webhook_url,
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
        "notification_channels": rule.notification_channels,
        "email_recipient": rule.email_recipient,
        "webhook_url": rule.webhook_url,
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
            "notification_channels": r.notification_channels,
            "email_recipient": r.email_recipient,
            "webhook_url": r.webhook_url,
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


@router.post("/evaluate", summary="Trigger evaluation of all active alert rules")
async def trigger_alert_evaluation(
    request: Request,
    current_user: CurrentUser,
) -> dict[str, Any]:
    db = request.app.state.db
    settings = request.app.state.settings
    summary = await evaluate_alert_rules(db, settings)
    return summary


@router.get("/events", summary="List triggered alert notification events")
async def list_alert_events(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    stmt = (
        select(AlertEvent)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        .options(selectinload(AlertEvent.deliveries))
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
            "deliveries": [
                {
                    "id": str(d.id),
                    "channel": d.channel,
                    "status": d.status,
                    "recipient": d.recipient,
                    "attempts": d.attempts,
                    "last_error": d.last_error,
                    "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
                }
                for d in e.deliveries
            ],
        }
        for e in events
    ]


@router.get("/deliveries", summary="Audit log of alert notification delivery dispatches")
async def list_alert_deliveries(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    stmt = (
        select(AlertDelivery)
        .join(AlertEvent, AlertDelivery.event_id == AlertEvent.id)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        .where(AlertRule.tenant_id == current_user.tenant_id)
        .order_by(desc(AlertDelivery.created_at))
        .limit(limit)
    )
    deliveries = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(d.id),
            "event_id": str(d.event_id),
            "channel": d.channel,
            "status": d.status,
            "recipient": d.recipient,
            "attempts": d.attempts,
            "last_error": d.last_error,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in deliveries
    ]
