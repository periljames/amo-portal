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


def _has_column(table_name: str, column_name: str) -> bool:
    """Return whether an earlier branch/head already materialised a column.

    The repository has historical Alembic heads that can converge on the same
    physical Workforce column. Keep this merge-path migration safe on a clean
    all-head upgrade without masking any incompatible type/default change.
    """

    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(str(column.get("name")) == column_name for column in columns)


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
