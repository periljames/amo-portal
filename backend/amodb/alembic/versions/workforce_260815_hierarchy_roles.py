"""Add governed Workforce role-source and management hierarchy metadata.

Revision ID: workforce_260815_hierarchy
Revises: roster_260815_shift_scope
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "workforce_260815_hierarchy"
down_revision = "roster_260815_shift_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workforce_positions",
        sa.Column("role_source", sa.String(length=24), nullable=False, server_default="TENANT"),
    )
    op.add_column(
        "workforce_positions",
        sa.Column("role_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workforce_positions",
        sa.Column("management_level", sa.String(length=24), nullable=False, server_default="STAFF"),
    )
    op.execute(
        "UPDATE workforce_positions SET management_level = 'SUPERVISOR' "
        "WHERE is_supervisory = TRUE"
    )
    op.create_check_constraint(
        "ck_workforce_position_role_source",
        "workforce_positions",
        "role_source IN ('TENANT', 'KCAR_2025')",
    )
    op.create_check_constraint(
        "ck_workforce_position_management_level",
        "workforce_positions",
        "management_level IN ('STAFF', 'SUPERVISOR', 'MANAGER', 'EXECUTIVE')",
    )
    op.create_unique_constraint(
        "uq_workforce_position_role_key",
        "workforce_positions",
        ["amo_id", "role_key"],
    )
    op.create_index(
        "ix_workforce_position_hierarchy",
        "workforce_positions",
        ["amo_id", "role_source", "management_level", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workforce_position_hierarchy", table_name="workforce_positions")
    op.drop_constraint("uq_workforce_position_role_key", "workforce_positions", type_="unique")
    op.drop_constraint("ck_workforce_position_management_level", "workforce_positions", type_="check")
    op.drop_constraint("ck_workforce_position_role_source", "workforce_positions", type_="check")
    op.drop_column("workforce_positions", "management_level")
    op.drop_column("workforce_positions", "role_key")
    op.drop_column("workforce_positions", "role_source")
