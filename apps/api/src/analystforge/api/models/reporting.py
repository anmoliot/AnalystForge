"""Report artifact persistence and metadata (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from analystforge.api.db import Base
from analystforge.api.models.base import uuid_pk


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        Index("ix_report_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)  # TEARSHEET, DCF_SUMMARY, PORTFOLIO_RISK, BACKTEST_PERFORMANCE
    ticker: Mapped[str | None] = mapped_column(String(32), index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="PDF")  # PDF, CSV, MARKDOWN, JSON
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="COMPLETED")  # PENDING, COMPLETED, FAILED
    content: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
