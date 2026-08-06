"""Add governed Workforce hierarchy, positions, placements and offboarding.

Revision ID: workforce_20260806_governance
Revises: workforce_20260806_bulk_ops
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "workforce_20260806_governance"
down_revision: Union[str, Sequence[str], None] = "workforce_20260806_bulk_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workforce_org_units",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("legacy_department_id", sa.String(length=36), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit_type", sa.String(length=32), nullable=False, server_default="TEAM"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_workforce_org_unit_not_self"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["workforce_org_units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["legacy_department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_workforce_org_unit_code"),
    )
    op.create_index("ix_workforce_org_unit_parent", "workforce_org_units", ["amo_id", "parent_id", "is_active"])
    op.create_index("ix_workforce_org_unit_type", "workforce_org_units", ["amo_id", "unit_type", "is_active"])
    op.create_index("ix_workforce_org_units_amo_id", "workforce_org_units", ["amo_id"])
    op.create_index("ix_workforce_org_units_parent_id", "workforce_org_units", ["parent_id"])
    op.create_index("ix_workforce_org_units_legacy_department_id", "workforce_org_units", ["legacy_department_id"])

    op.create_table(
        "workforce_job_families",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_workforce_job_family_code"),
    )
    op.create_index("ix_workforce_job_family_active", "workforce_job_families", ["amo_id", "is_active", "name"])
    op.create_index("ix_workforce_job_families_amo_id", "workforce_job_families", ["amo_id"])

    op.create_table(
        "workforce_grades",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rank_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_workforce_grade_code"),
    )
    op.create_index("ix_workforce_grade_active", "workforce_grades", ["amo_id", "is_active", "rank_order"])
    op.create_index("ix_workforce_grades_amo_id", "workforce_grades", ["amo_id"])

    op.create_table(
        "workforce_positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("canonical_title", sa.String(length=255), nullable=False),
        sa.Column("job_family_id", sa.String(length=36), nullable=True),
        sa.Column("grade_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_supervisory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_family_id"], ["workforce_job_families.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grade_id"], ["workforce_grades.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_workforce_position_code"),
    )
    op.create_index("ix_workforce_position_family_grade", "workforce_positions", ["amo_id", "job_family_id", "grade_id"])
    op.create_index("ix_workforce_position_active_title", "workforce_positions", ["amo_id", "is_active", "canonical_title"])
    op.create_index("ix_workforce_positions_amo_id", "workforce_positions", ["amo_id"])
    op.create_index("ix_workforce_positions_job_family_id", "workforce_positions", ["job_family_id"])
    op.create_index("ix_workforce_positions_grade_id", "workforce_positions", ["grade_id"])

    op.create_table(
        "workforce_person_placements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("org_unit_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("preferred_title", sa.String(length=255), nullable=True),
        sa.Column("placement_type", sa.String(length=24), nullable=False, server_default="PRIMARY"),
        sa.Column("base_station_id", sa.String(length=36), nullable=True),
        sa.Column("supervisor_user_id", sa.String(length=36), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_workforce_placement_dates"),
        sa.CheckConstraint("supervisor_user_id IS NULL OR supervisor_user_id <> user_id", name="ck_workforce_placement_not_self_supervised"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_unit_id"], ["workforce_org_units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["position_id"], ["workforce_positions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supervisor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "amo_id", "user_id", "placement_type", "org_unit_id", "effective_from",
            name="uq_workforce_person_placement",
        ),
    )
    op.create_index("ix_workforce_placement_user_effective", "workforce_person_placements", ["amo_id", "user_id", "effective_from", "effective_to"])
    op.create_index("ix_workforce_placement_org_effective", "workforce_person_placements", ["amo_id", "org_unit_id", "effective_from", "effective_to"])
    op.create_index("ix_workforce_placement_position", "workforce_person_placements", ["amo_id", "position_id", "effective_from", "effective_to"])
    op.create_index("ix_workforce_placement_supervisor", "workforce_person_placements", ["amo_id", "supervisor_user_id", "effective_from", "effective_to"])
    op.create_index("ix_workforce_placement_base", "workforce_person_placements", ["amo_id", "base_station_id", "effective_from", "effective_to"])
    op.create_index("ix_workforce_person_placements_amo_id", "workforce_person_placements", ["amo_id"])
    op.create_index("ix_workforce_person_placements_user_id", "workforce_person_placements", ["user_id"])

    op.create_table(
        "workforce_offboarding_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="SCHEDULED"),
        sa.Column("revoke_access", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("end_contracts", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("remove_groups", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "user_id", "effective_on", name="uq_workforce_offboarding_user_date"),
    )
    op.create_index("ix_workforce_offboarding_due", "workforce_offboarding_plans", ["amo_id", "status", "effective_on"])
    op.create_index("ix_workforce_offboarding_plans_amo_id", "workforce_offboarding_plans", ["amo_id"])
    op.create_index("ix_workforce_offboarding_plans_user_id", "workforce_offboarding_plans", ["user_id"])


def downgrade() -> None:
    op.drop_table("workforce_offboarding_plans")
    op.drop_table("workforce_person_placements")
    op.drop_table("workforce_positions")
    op.drop_table("workforce_grades")
    op.drop_table("workforce_job_families")
    op.drop_table("workforce_org_units")
