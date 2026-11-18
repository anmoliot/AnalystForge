"""Backtest run persistence (Phase 7)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analystforge.api.db import Base
from analystforge.api.models.base import TimestampMixin, uuid_pk


class BacktestRun(Base, TimestampMixin):
    __tablename__ = "backtest_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    final_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_return: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    cagr: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    max_drawdown: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    win_rate: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    trades_count: Mapped[int] = mapped_column(default=0, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    equity_curve: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    trades: Mapped[list[BacktestTrade]] = relationship(
        "BacktestTrade", back_populates="run", cascade="all, delete-orphan"
    )


class BacktestTrade(Base, TimestampMixin):
    __tablename__ = "backtest_trades"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_type: Mapped[str] = mapped_column(String(16), default="LONG", nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    run: Mapped[BacktestRun] = relationship("BacktestRun", back_populates="trades")
