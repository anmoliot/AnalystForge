"""portfolio tables

Revision ID: 0005_portfolio_tables
Revises: 0004_valuation_tables
Create Date: 2026-11-15 12:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_portfolio_tables"
down_revision: str | None = "0004_valuation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_currency", sa.String(length=8), server_default="USD", nullable=False),
        sa.Column("benchmark_ticker", sa.String(length=32), server_default="SPY", nullable=False),
        sa.Column("cost_basis_method", sa.String(length=16), server_default="FIFO", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolios_tenant_id"), "portfolios", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_portfolios_user_id"), "portfolios", ["user_id"], unique=False)

    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="USD", nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), server_default="1.0", nullable=False),
        sa.Column("commission", sa.Numeric(precision=18, scale=4), server_default="0.0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "external_id", name="uq_portfolio_transactions_portfolio_external"
        ),
    )
    op.create_index(op.f("ix_portfolio_transactions_portfolio_id"), "portfolio_transactions", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_portfolio_transactions_ticker"), "portfolio_transactions", ["ticker"], unique=False)
    op.create_index(op.f("ix_portfolio_transactions_trade_date"), "portfolio_transactions", ["trade_date"], unique=False)


def downgrade() -> None:
    op.drop_table("portfolio_transactions")
    op.drop_table("portfolios")
