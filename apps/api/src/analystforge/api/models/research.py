"""SEC filings and XBRL facts (shared reference data)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from analystforge.api.db import Base
from analystforge.api.models.base import uuid_pk

_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (
        UniqueConstraint("instrument_id", "accession", name="uq_filings_instrument_accession"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    accession: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_of_report: Mapped[date | None] = mapped_column(Date)
    primary_document: Mapped[str] = mapped_column(String(255), nullable=False)
    document_url: Mapped[str] = mapped_column(String(500), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="sec_edgar")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FundamentalFact(Base):
    __tablename__ = "fundamental_facts"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "taxonomy",
            "concept",
            "unit",
            "period_start",
            "period_end",
            "accession",
            name="uq_fundamental_facts_identity",
        ),
        Index("ix_fundamental_facts_instrument_concept", "instrument_id", "concept"),
        Index("ix_fundamental_facts_period_end", "period_end"),
    )

    id: Mapped[int] = mapped_column(_BIGINT, Identity(), primary_key=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    taxonomy: Mapped[str] = mapped_column(String(32), nullable=False)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(38, 10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(SmallInteger)
    fiscal_period: Mapped[str | None] = mapped_column(String(8))
    form: Mapped[str] = mapped_column(String(16), nullable=False)
    filed: Mapped[date] = mapped_column(Date, nullable=False)
    frame: Mapped[str | None] = mapped_column(String(32))
    accession: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="sec_edgar")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
