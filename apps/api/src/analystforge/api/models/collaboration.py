"""Collaboration, watchlists, notes, and expiring share links models."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analystforge.api.db import Base
from analystforge.api.models.base import TimestampMixin, uuid_pk


def generate_share_token() -> str:
    """Generate cryptographically secure URL-safe share token."""
    return secrets.token_urlsafe(24)


class Watchlist(Base, TimestampMixin):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    items: Mapped[list[WatchlistItem]] = relationship(
        "WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    watchlist: Mapped[Watchlist] = relationship("Watchlist", back_populates="items")


class AnalystNote(Base, TimestampMixin):
    __tablename__ = "analyst_notes"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # "ticker", "portfolio", "screen", "macro"
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class ShareLink(Base, TimestampMixin):
    __tablename__ = "share_links"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(
        String(64), default=generate_share_token, unique=True, nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # "portfolio", "screen", "backtest", "valuation"
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
