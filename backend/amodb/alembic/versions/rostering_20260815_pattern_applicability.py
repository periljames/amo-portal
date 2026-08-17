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
    inspector = sa.inspect(op.get_bind())
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    # Earlier convergence/pre-create migrations can materialize the current
    # Workforce model before this branch-specific revision is reached.  Treat
    # the explicit applicability column as convergent schema: create it only
    # when it is genuinely absent instead of failing a clean ``upgrade heads``
    # with DuplicateColumn.
    if not _has_column("work_patterns", "applicability_json"):
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
