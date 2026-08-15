"""Scope roster shift templates to departments.

Revision ID: roster_260815_shift_scope
Revises: rostering_20260815_pattern_scope
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "roster_260815_shift_scope"
down_revision = "rostering_20260815_pattern_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shift_template_departments",
        sa.Column(
            "shift_template_id",
            sa.String(length=36),
            sa.ForeignKey("shift_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "department_id",
            sa.String(length=36),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "shift_template_id",
            "department_id",
            name="pk_shift_template_departments",
        ),
    )
    op.create_index(
        "ix_shift_template_departments_department",
        "shift_template_departments",
        ["department_id", "shift_template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shift_template_departments_department",
        table_name="shift_template_departments",
    )
    op.drop_table("shift_template_departments")
