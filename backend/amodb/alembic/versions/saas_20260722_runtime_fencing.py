"""Add queue lease fencing after messaging convergence.

Revision ID: saas_20260722_runtime_fence
Revises: saas_20260722_messaging
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "saas_20260722_runtime_fence"
down_revision = "saas_20260722_messaging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("saas_jobs"):
        raise RuntimeError("Runtime fencing requires the SaaS job table")
    columns = {str(column["name"]) for column in inspector.get_columns("saas_jobs")}
    if "lease_token" not in columns:
        op.add_column("saas_jobs", sa.Column("lease_token", sa.String(length=64), nullable=True))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_saas_jobs_lease_fence ON saas_jobs (id, status, lease_token)"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_saas_jobs_lease_fence"))
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("saas_jobs"):
        columns = {str(column["name"]) for column in inspector.get_columns("saas_jobs")}
        if "lease_token" in columns:
            op.drop_column("saas_jobs", "lease_token")
