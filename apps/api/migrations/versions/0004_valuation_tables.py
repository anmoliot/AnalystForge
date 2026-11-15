"""valuation tables

Revision ID: 0004_valuation_tables
Revises: 0003_auth_tables
Create Date: 2026-11-15 11:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_valuation_tables"
down_revision: str | None = "0003_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "valuation_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("model_type", sa.String(length=32), nullable=False, server_default="DCF"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_valuation_models_tenant_id"), "valuation_models", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_valuation_models_user_id"), "valuation_models", ["user_id"], unique=False)
    op.create_index(op.f("ix_valuation_models_ticker"), "valuation_models", ["ticker"], unique=False)

    op.create_table(
        "valuation_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False, server_default="base"),
        sa.Column("assumptions", _JSON, nullable=False),
        sa.Column("results", _JSON, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["valuation_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "version_number", name="uq_valuation_versions_model_version"),
    )
    op.create_index(op.f("ix_valuation_versions_model_id"), "valuation_versions", ["model_id"], unique=False)


def downgrade() -> None:
    op.drop_table("valuation_versions")
    op.drop_table("valuation_models")
