"""add forecast and package readiness

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-08-04 15:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f6g7h8i9j0k1"
down_revision = "e5f6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_forecast_scenarios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("default_daily_hours", sa.Numeric(10, 2), nullable=False, server_default="5"),
        sa.Column("default_daily_cycles", sa.Numeric(10, 2), nullable=False, server_default="3"),
        sa.Column("aircraft_assumptions_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "name", name="uq_forecast_scenario_amo_name"),
        sa.CheckConstraint("horizon_days >= 1", name="ck_forecast_scenario_horizon"),
        sa.CheckConstraint("default_daily_hours >= 0", name="ck_forecast_scenario_daily_hours"),
        sa.CheckConstraint("default_daily_cycles >= 0", name="ck_forecast_scenario_daily_cycles"),
    )
    op.create_index("ix_forecast_scenarios_amo_status", "planning_forecast_scenarios", ["amo_id", "status"])

    op.create_table(
        "planning_forecast_scenario_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("planning_forecast_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("registration", sa.String(length=20), nullable=False),
        sa.Column("program_item_id", sa.Integer(), sa.ForeignKey("amp_program_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_program_item_id", sa.Integer(), sa.ForeignKey("amp_aircraft_program_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_code", sa.String(length=64), nullable=True),
        sa.Column("task_title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("projected_due_date", sa.Date(), nullable=True),
        sa.Column("projected_trigger", sa.String(length=16), nullable=True),
        sa.Column("projected_days", sa.Numeric(12, 2), nullable=True),
        sa.Column("remaining_hours", sa.Numeric(14, 2), nullable=True),
        sa.Column("remaining_cycles", sa.Numeric(14, 2), nullable=True),
        sa.Column("remaining_days", sa.Numeric(14, 2), nullable=True),
        sa.Column("daily_hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("daily_cycles", sa.Numeric(10, 2), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scenario_id", "aircraft_program_item_id", name="uq_forecast_scenario_item"),
    )
    op.create_index("ix_forecast_items_scenario_due", "planning_forecast_scenario_items", ["scenario_id", "projected_due_date"])
    op.create_index("ix_forecast_items_aircraft", "planning_forecast_scenario_items", ["amo_id", "aircraft_serial_number"])

    op.create_table(
        "work_package_readiness_requirements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_package_id", sa.Integer(), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity_required", sa.Numeric(12, 2), nullable=False, server_default="1"),
        sa.Column("quantity_confirmed", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="REQUIRED"),
        sa.Column("required_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_required >= 0", name="ck_package_requirement_quantity_required"),
        sa.CheckConstraint("quantity_confirmed >= 0", name="ck_package_requirement_quantity_confirmed"),
    )
    op.create_index("ix_package_requirements_package_status", "work_package_readiness_requirements", ["work_package_id", "status"])
    op.create_index("ix_package_requirements_amo_category", "work_package_readiness_requirements", ["amo_id", "category"])

    op.create_table(
        "work_package_readiness_assessments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_package_id", sa.Integer(), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("assessed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("work_package_id", "version", name="uq_package_assessment_version"),
    )
    op.create_index("ix_package_assessments_package", "work_package_readiness_assessments", ["work_package_id", "version"])

    op.create_table(
        "work_package_freezes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_package_id", sa.Integer(), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("frozen_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("work_package_id", "version", name="uq_package_freeze_version"),
    )
    op.create_index("ix_package_freezes_package_status", "work_package_freezes", ["work_package_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_package_freezes_package_status", table_name="work_package_freezes")
    op.drop_table("work_package_freezes")
    op.drop_index("ix_package_assessments_package", table_name="work_package_readiness_assessments")
    op.drop_table("work_package_readiness_assessments")
    op.drop_index("ix_package_requirements_amo_category", table_name="work_package_readiness_requirements")
    op.drop_index("ix_package_requirements_package_status", table_name="work_package_readiness_requirements")
    op.drop_table("work_package_readiness_requirements")
    op.drop_index("ix_forecast_items_aircraft", table_name="planning_forecast_scenario_items")
    op.drop_index("ix_forecast_items_scenario_due", table_name="planning_forecast_scenario_items")
    op.drop_table("planning_forecast_scenario_items")
    op.drop_index("ix_forecast_scenarios_amo_status", table_name="planning_forecast_scenarios")
    op.drop_table("planning_forecast_scenarios")
