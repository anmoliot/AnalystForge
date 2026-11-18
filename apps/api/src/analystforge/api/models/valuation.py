"""Valuation models and versioned audit history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analystforge.api.db import Base
from analystforge.api.models.base import TimestampMixin, uuid_pk

_JSON = JSON().with_variant(JSONB, "postgresql")


class ValuationModel(Base, TimestampMixin):
    __tablename__ = "valuation_models"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False, default="DCF")
    description: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list[ValuationVersion]] = relationship(
        back_populates="model",
        cascade="all, delete-orphan",
        order_by="desc(ValuationVersion.version_number)",
    )


class ValuationVersion(Base):
    __tablename__ = "valuation_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version_number", name="uq_valuation_versions_model_version"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("valuation_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario: Mapped[str] = mapped_column(String(32), nullable=False, default="base")
    assumptions: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model: Mapped[ValuationModel] = relationship(back_populates="versions")
