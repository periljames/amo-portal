"""Add supporting-auditor teams to annual audit programme items.

Revision ID: quality_260905_programme_team
Revises: quality_260905_area_catalogue
Create Date: 2026-09-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260905_programme_team"
down_revision = "quality_260905_area_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_audit_programme_items",
        sa.Column(
            "supporting_auditor_user_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "qms_audits",
        sa.Column(
            "supporting_auditor_user_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column("qms_audits", sa.Column("location", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("qms_audits", "location")
    op.drop_column("qms_audits", "supporting_auditor_user_ids")
    op.drop_column("quality_audit_programme_items", "supporting_auditor_user_ids")
