"""Portfolio and transaction models with multi-currency and cost-basis tracking."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analystforge.api.db import Base
from analystforge.api.models.base import TimestampMixin, uuid_pk


class Portfolio(Base, TimestampMixin):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    benchmark_ticker: Mapped[str] = mapped_column(String(32), nullable=False, default="SPY")
    cost_basis_method: Mapped[str] = mapped_column(String(16), nullable=False, default="FIFO")

    transactions: Mapped[list[PortfolioTransaction]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan", order_by="PortfolioTransaction.trade_date"
    )


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "external_id", name="uq_portfolio_transactions_portfolio_external"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)  # BUY, SELL, DIVIDEND, SPLIT, FEE
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1.0"))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0"))
    notes: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")
