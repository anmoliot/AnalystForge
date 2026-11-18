"""Saved screens, alert rules and triggered alert persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analystforge.api.db import Base
from analystforge.api.models.base import TimestampMixin, uuid_pk


class SavedScreen(Base, TimestampMixin):
    __tablename__ = "saved_screens"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    schedule: Mapped[str | None] = mapped_column(String(32), nullable=True)  # daily, weekly, None
    notify_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertRule(Base, TimestampMixin):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # PRICE_ABOVE, PRICE_BELOW, PE_ABOVE, PE_BELOW
    target_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notification_channels: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["in_app"], nullable=False
    )  # ["in_app", "email", "webhook"]
    email_recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    events: Mapped[list[AlertEvent]] = relationship(
        "AlertEvent", back_populates="rule", cascade="all, delete-orphan"
    )


class AlertEvent(Base, TimestampMixin):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    triggered_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    rule: Mapped[AlertRule] = relationship("AlertRule", back_populates="events")
    deliveries: Mapped[list[AlertDelivery]] = relationship(
        "AlertDelivery", back_populates="event", cascade="all, delete-orphan"
    )


class AlertDelivery(Base, TimestampMixin):
    __tablename__ = "alert_deliveries"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # in_app, email, webhook
    status: Mapped[str] = mapped_column(
        String(32), default="delivered", nullable=False
    )  # delivered, failed, retrying
    recipient: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # email address or webhook URL
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped[AlertEvent] = relationship("AlertEvent", back_populates="deliveries")
