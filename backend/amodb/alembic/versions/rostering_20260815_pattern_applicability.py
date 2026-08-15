"""Add explicit automatic applicability to Workforce work patterns.

Revision ID: rostering_20260815_pattern_scope
Revises: roster_training_260814_merge
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "rostering_20260815_pattern_scope"
down_revision = "roster_training_260814_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_patterns",
        sa.Column(
            "applicability_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("work_patterns", "applicability_json")
