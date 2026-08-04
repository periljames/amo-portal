"""add phase two records packages

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-08-04 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6g7h8"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aircraft_usage_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usage_id", sa.Integer(), sa.ForeignKey("aircraft_usage.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_values_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("expected_usage_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_usage_corrections_amo_status", "aircraft_usage_corrections", ["amo_id", "status"])
    op.create_index("ix_usage_corrections_usage", "aircraft_usage_corrections", ["usage_id", "requested_at"])

    op.create_table(
        "work_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_ref", sa.String(length=64), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("check_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_horizon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("baseline_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("readiness_status", sa.String(length=24), nullable=False, server_default="NOT_CHECKED"),
        sa.Column("readiness_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "package_ref", name="uq_work_packages_amo_ref"),
        sa.CheckConstraint("planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start", name="ck_work_packages_date_order"),
        sa.CheckConstraint("source_horizon_days >= 1", name="ck_work_packages_horizon_positive"),
    )
    op.create_index("ix_work_packages_amo_status", "work_packages", ["amo_id", "status"])
    op.create_index("ix_work_packages_amo_aircraft", "work_packages", ["amo_id", "aircraft_serial_number"])

    op.create_table(
        "work_package_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_package_id", sa.Integer(), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="MANUAL"),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("added_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("work_package_id", "work_order_id", name="uq_work_package_order"),
    )
    op.create_index("ix_work_package_orders_package", "work_package_orders", ["work_package_id", "sequence_no"])
    op.create_index("ix_work_package_orders_order", "work_package_orders", ["work_order_id"])

    op.create_table(
        "amp_program_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_code", sa.String(length=50), nullable=False),
        sa.Column("revision_code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "template_code", "revision_code", name="uq_amp_revision_identity"),
    )
    op.create_index("ix_amp_revisions_amo_status", "amp_program_revisions", ["amo_id", "status"])

    op.create_table(
        "amp_aircraft_baselines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", sa.Integer(), sa.ForeignKey("amp_program_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_code", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("applied_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_amp_baselines_amo_aircraft", "amp_aircraft_baselines", ["amo_id", "aircraft_serial_number", "status"])


def downgrade() -> None:
    op.drop_index("ix_amp_baselines_amo_aircraft", table_name="amp_aircraft_baselines")
    op.drop_table("amp_aircraft_baselines")
    op.drop_index("ix_amp_revisions_amo_status", table_name="amp_program_revisions")
    op.drop_table("amp_program_revisions")
    op.drop_index("ix_work_package_orders_order", table_name="work_package_orders")
    op.drop_index("ix_work_package_orders_package", table_name="work_package_orders")
    op.drop_table("work_package_orders")
    op.drop_index("ix_work_packages_amo_aircraft", table_name="work_packages")
    op.drop_index("ix_work_packages_amo_status", table_name="work_packages")
    op.drop_table("work_packages")
    op.drop_index("ix_usage_corrections_usage", table_name="aircraft_usage_corrections")
    op.drop_index("ix_usage_corrections_amo_status", table_name="aircraft_usage_corrections")
    op.drop_table("aircraft_usage_corrections")
