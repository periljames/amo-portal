"""Enable continuous hybrid audit-programme optimisation.

Revision ID: quality_260823_hybrid_programme
Revises: quality_260820_provider_gov
Create Date: 2026-08-23

The programme no longer asks a tenant to choose compliance, performance or
risk as mutually exclusive methods. Compliance is the permanent baseline and
risk/performance signals adapt surveillance priority above that floor.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260823_hybrid_programme"
down_revision = "quality_260820_provider_gov"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_audit_programmes",
        sa.Column("continuous_monitoring_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "quality_audit_programmes",
        sa.Column("optimizer_version", sa.String(length=64), server_default="HYBRID_ASSURANCE_V1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("quality_audit_programmes", "optimizer_version")
    op.drop_column("quality_audit_programmes", "continuous_monitoring_enabled")
