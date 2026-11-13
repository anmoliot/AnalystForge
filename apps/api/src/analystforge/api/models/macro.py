"""Macro series and FX rates (shared reference data)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from analystforge.api.db import Base


class MacroSeries(Base):
    __tablename__ = "macro_series"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    units: Mapped[str] = mapped_column(String(300), nullable=False)
    frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MacroObservation(Base):
    __tablename__ = "macro_observations"

    series_code: Mapped[str] = mapped_column(
        ForeignKey("macro_series.code", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    provider: Mapped[str] = mapped_column(String(16), nullable=False)


class FxRate(Base):
    __tablename__ = "fx_rates"

    base: Mapped[str] = mapped_column(String(8), primary_key=True)
    quote: Mapped[str] = mapped_column(String(8), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
