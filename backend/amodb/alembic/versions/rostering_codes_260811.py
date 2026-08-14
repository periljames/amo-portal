"""Add tenant roster code policy and direct aircraft allocations.

Revision ID: rostering_codes_260811
Revises: docctl_ai_audit_260809
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "rostering_codes_260811"
down_revision = "docctl_ai_audit_260809"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roster_shift_template_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("shift_template_id", sa.String(length=36), nullable=False),
        sa.Column("unpaid_break_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calendar_mode", sa.String(length=16), nullable=False, server_default="TIMED"),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("unpaid_break_minutes >= 0", name="ck_roster_shift_policy_break_nonneg"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_roster_shift_policy_effective_dates",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_template_id"], ["shift_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shift_template_id", name="uq_roster_shift_policy_template"),
    )
    op.create_index(
        "ix_roster_shift_policy_amo",
        "roster_shift_template_policies",
        ["amo_id", "shift_template_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_roster_shift_template_policies_amo_id"),
        "roster_shift_template_policies",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_roster_shift_template_policies_shift_template_id"),
        "roster_shift_template_policies",
        ["shift_template_id"],
        unique=False,
    )

    op.create_table(
        "roster_aircraft_allocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("roster_assignment_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("allocation_type", sa.String(length=32), nullable=False, server_default="FLIGHT_ENGINEERING"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_roster_aircraft_alloc_time_order"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roster_assignment_id"], ["roster_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "roster_assignment_id",
            "aircraft_serial_number",
            "starts_at",
            "ends_at",
            name="uq_roster_aircraft_allocation_window",
        ),
    )
    op.create_index(
        "ix_roster_aircraft_alloc_amo_assignment",
        "roster_aircraft_allocations",
        ["amo_id", "roster_assignment_id"],
        unique=False,
    )
    op.create_index(
        "ix_roster_aircraft_alloc_aircraft_time",
        "roster_aircraft_allocations",
        ["aircraft_serial_number", "starts_at", "ends_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_roster_aircraft_allocations_amo_id"),
        "roster_aircraft_allocations",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_roster_aircraft_allocations_roster_assignment_id"),
        "roster_aircraft_allocations",
        ["roster_assignment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_roster_aircraft_allocations_aircraft_serial_number"),
        "roster_aircraft_allocations",
        ["aircraft_serial_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_roster_aircraft_allocations_aircraft_serial_number"), table_name="roster_aircraft_allocations")
    op.drop_index(op.f("ix_roster_aircraft_allocations_roster_assignment_id"), table_name="roster_aircraft_allocations")
    op.drop_index(op.f("ix_roster_aircraft_allocations_amo_id"), table_name="roster_aircraft_allocations")
    op.drop_index("ix_roster_aircraft_alloc_aircraft_time", table_name="roster_aircraft_allocations")
    op.drop_index("ix_roster_aircraft_alloc_amo_assignment", table_name="roster_aircraft_allocations")
    op.drop_table("roster_aircraft_allocations")

    op.drop_index(op.f("ix_roster_shift_template_policies_shift_template_id"), table_name="roster_shift_template_policies")
    op.drop_index(op.f("ix_roster_shift_template_policies_amo_id"), table_name="roster_shift_template_policies")
    op.drop_index("ix_roster_shift_policy_amo", table_name="roster_shift_template_policies")
    op.drop_table("roster_shift_template_policies")
