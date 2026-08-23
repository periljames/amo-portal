"""Persist the audit programme planning methodology.

Revision ID: quality_260823_programme_method
Revises: quality_260820_provider_gov
Create Date: 2026-08-23

Existing programmes are backfilled as COMPLIANCE because the legacy workflow
was explicitly conformity/regulatory driven. New programmes can select
COMPLIANCE, PERFORMANCE or RISK as their primary planning methodology while
retaining mandatory regulatory coverage in every case.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260823_programme_method"
down_revision = "quality_260820_provider_gov"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_audit_programmes",
        sa.Column("programme_methodology", sa.String(length=20), server_default="COMPLIANCE", nullable=False),
    )
    op.add_column(
        "quality_audit_programmes",
        sa.Column("methodology_rationale", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_methodology",
        "quality_audit_programmes",
        "programme_methodology IN ('COMPLIANCE','PERFORMANCE','RISK')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_quality_audit_programme_methodology",
        "quality_audit_programmes",
        type_="check",
    )
    op.drop_column("quality_audit_programmes", "methodology_rationale")
    op.drop_column("quality_audit_programmes", "programme_methodology")
