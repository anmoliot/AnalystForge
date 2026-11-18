"""Correlate audit events with HTTP responses. Existing rows retain unknown values."""

import sqlalchemy as sa
from alembic import op

revision = "0006_audit_request"
down_revision = "0005_portfolio_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_log", sa.Column("request_id", sa.String(128)))
    op.add_column("audit_log", sa.Column("status_code", sa.Integer()))
    op.create_index("ix_audit_log_request_id", "audit_log", ["request_id"])


def downgrade():
    op.drop_index("ix_audit_log_request_id", table_name="audit_log")
    op.drop_column("audit_log", "status_code")
    op.drop_column("audit_log", "request_id")
