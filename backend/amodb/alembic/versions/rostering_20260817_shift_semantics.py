"""Add explicit tenant-configurable roster shift semantics.

Revision ID: rostering_260817_shift_semantics
Revises: rostering_260817_extension
Create Date: 2026-08-17

These fields describe tenant scheduling semantics only. ``counts_as_rest`` is
never treated as proof that statutory protected rest occurred; the compliance
engine still establishes rest from the absence of effective duty intervals.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_260817_shift_semantics"
down_revision = "rostering_260817_extension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roster_shift_template_policies",
        sa.Column("counts_as_rest", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "roster_shift_template_policies",
        sa.Column("on_site_availability", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "roster_shift_template_policies",
        sa.Column("scheduling_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.execute(
        sa.text(
            """
            UPDATE roster_shift_template_policies
               SET counts_as_rest = TRUE
             WHERE duty_semantic IN ('REST', 'OFF')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE roster_shift_template_policies
               SET on_site_availability = TRUE
             WHERE duty_semantic = 'STANDBY'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("roster_shift_template_policies", "scheduling_eligible")
    op.drop_column("roster_shift_template_policies", "on_site_availability")
    op.drop_column("roster_shift_template_policies", "counts_as_rest")
