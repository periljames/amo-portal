"""Add explicit automatic applicability to Workforce work patterns.

Revision ID: rostering_20260815_pattern_scope
Revises: roster_training_260814_merge
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "rostering_20260815_pattern_scope"
down_revision = "roster_training_260814_merge"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    """Handle clean installs where an older metadata-driven migration already
    created a column from the current application model.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return False
    return column_name in {str(column["name"]) for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_column("work_patterns", "applicability_json"):
        return
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
    if _has_column("work_patterns", "applicability_json"):
        op.drop_column("work_patterns", "applicability_json")
