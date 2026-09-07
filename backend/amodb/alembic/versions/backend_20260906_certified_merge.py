"""Merge active backend branches and repair undated audit time defaults.

Revision ID: backend_260906_certified
Revises: platform_20260903_netprobe, quality_260905_prog_approval,
         quality_260905_prog_observer
Create Date: 2026-09-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "backend_260906_certified"
down_revision = (
    "platform_20260903_netprobe",
    "quality_260905_prog_approval",
    "quality_260905_prog_observer",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE qms_audits SET planned_start_time = NULL "
            "WHERE planned_start IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE qms_audits SET planned_end_time = NULL "
            "WHERE planned_end IS NULL"
        )
    )
    op.alter_column("qms_audits", "planned_start_time", server_default=None)
    op.alter_column("qms_audits", "planned_end_time", server_default=None)


def downgrade() -> None:
    op.alter_column(
        "qms_audits",
        "planned_start_time",
        server_default=sa.text("'09:00:00'"),
    )
    op.alter_column(
        "qms_audits",
        "planned_end_time",
        server_default=sa.text("'17:00:00'"),
    )
