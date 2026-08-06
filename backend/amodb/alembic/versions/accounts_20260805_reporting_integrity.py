"""Strengthen reporting assignment and organization-unit integrity.

Revision ID: accounts_20260805_reporting_integrity
Revises: accounts_20260805_reporting_lines
Create Date: 2026-08-05
"""
from __future__ import annotations

from alembic import op

revision = "accounts_20260805_reporting_integrity"
down_revision = "accounts_20260805_reporting_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_organization_units_base_station_id",
        "organization_units",
        "base_stations",
        ["base_station_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_position_assignments_effective_period",
        "position_assignments",
        "effective_to IS NULL OR effective_to >= effective_from",
    )
    op.create_check_constraint(
        "ck_position_assignments_matrix_reason",
        "position_assignments",
        "matrix_reporting = false OR length(trim(coalesce(matrix_reason, ''))) > 0",
    )
    op.create_check_constraint(
        "ck_workforce_engagements_effective_period",
        "workforce_engagements",
        "end_date IS NULL OR end_date >= start_date",
    )
    op.create_check_constraint(
        "ck_personnel_title_preferences_status",
        "personnel_title_preferences",
        "status IN ('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'SUPERSEDED')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_personnel_title_preferences_status",
        "personnel_title_preferences",
        type_="check",
    )
    op.drop_constraint(
        "ck_workforce_engagements_effective_period",
        "workforce_engagements",
        type_="check",
    )
    op.drop_constraint(
        "ck_position_assignments_matrix_reason",
        "position_assignments",
        type_="check",
    )
    op.drop_constraint(
        "ck_position_assignments_effective_period",
        "position_assignments",
        type_="check",
    )
    op.drop_constraint(
        "fk_organization_units_base_station_id",
        "organization_units",
        type_="foreignkey",
    )
