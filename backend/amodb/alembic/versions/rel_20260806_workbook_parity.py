"""Add controlled Reliability workbook-parity registers and reports.

Revision ID: rel_20260806_workbook_parity
Revises: rel_20260806_formula_snapshots
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "rel_20260806_workbook_parity"
down_revision = "rel_20260806_formula_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reliability_workbook_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_code", sa.String(length=24), nullable=False),
        sa.Column("record_number", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_end_date", sa.Date(), nullable=True),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="SET NULL"), nullable=True),
        sa.Column("ata_chapter", sa.String(length=20), nullable=True),
        sa.Column("reference_code", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("derived_values", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_workbook", sa.String(length=255), nullable=True),
        sa.Column("source_sheet", sa.String(length=128), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("canonical_event_id", sa.Integer(), sa.ForeignKey("reliability_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("closed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "dataset_code", "record_number", "revision", name="uq_rel_workbook_record_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_rel_workbook_revision_positive"),
        sa.CheckConstraint("source_row_number IS NULL OR source_row_number >= 1", name="ck_rel_workbook_source_row_positive"),
        sa.CheckConstraint("event_end_date IS NULL OR event_end_date >= event_date", name="ck_rel_workbook_dates"),
        sa.CheckConstraint("dataset_code IN ('AU','AI','PM','OOS','RM','SM','STRUCTURES','RECURRING','ECTM')", name="ck_rel_workbook_dataset"),
        sa.CheckConstraint("status IN ('DRAFT','APPROVED','CLOSED','REJECTED')", name="ck_rel_workbook_status"),
    )
    op.create_index("ix_rel_workbook_records_scope_date", "reliability_workbook_records", ["amo_id", "dataset_code", "event_date"])
    op.create_index("ix_rel_workbook_records_aircraft", "reliability_workbook_records", ["amo_id", "aircraft_serial_number", "event_date"])
    op.create_index("ix_rel_workbook_records_status", "reliability_workbook_records", ["amo_id", "dataset_code", "status"])
    op.create_index("ix_reliability_workbook_records_source_hash", "reliability_workbook_records", ["source_hash"])
    op.create_index("ix_reliability_workbook_records_canonical_event_id", "reliability_workbook_records", ["canonical_event_id"])

    op.create_table(
        "reliability_workbook_field_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("workbook_family", sa.String(length=64), nullable=False),
        sa.Column("dataset_code", sa.String(length=24), nullable=False),
        sa.Column("source_sheet", sa.String(length=128), nullable=False),
        sa.Column("source_column", sa.String(length=255), nullable=False),
        sa.Column("canonical_field", sa.String(length=128), nullable=False),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("aliases", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transform", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "profile_code", "dataset_code", "source_sheet", "source_column", name="uq_rel_workbook_field_mapping"),
        sa.CheckConstraint("dataset_code IN ('AU','AI','PM','OOS','RM','SM','STRUCTURES','RECURRING','ECTM')", name="ck_rel_workbook_mapping_dataset"),
    )
    op.create_index("ix_rel_workbook_mapping_profile", "reliability_workbook_field_mappings", ["amo_id", "profile_code"])

    op.create_table(
        "reliability_statistical_alert_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_code", sa.String(length=128), nullable=False),
        sa.Column("metric_label", sa.String(length=255), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("dataset_code", sa.String(length=24), nullable=True),
        sa.Column("metric_field", sa.String(length=128), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="FLEET"),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("bucket", sa.String(length=16), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("mean_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("sample_stddev", sa.Numeric(20, 6), nullable=False),
        sa.Column("warning_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("alert_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("warning_level", sa.Numeric(20, 6), nullable=False),
        sa.Column("alert_level", sa.Numeric(20, 6), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("series", JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("generated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("period_end >= period_start", name="ck_rel_stat_alert_dates"),
        sa.CheckConstraint("sample_size >= 2", name="ck_rel_stat_alert_sample"),
        sa.CheckConstraint("sample_stddev >= 0", name="ck_rel_stat_alert_stddev"),
        sa.CheckConstraint("alert_multiplier >= warning_multiplier AND warning_multiplier >= 0", name="ck_rel_stat_alert_multipliers"),
    )
    op.create_index("ix_rel_stat_alert_metric_scope", "reliability_statistical_alert_results", ["amo_id", "metric_code", "scope_type", "scope_value"])
    op.create_index("ix_rel_stat_alert_period", "reliability_statistical_alert_results", ["amo_id", "period_start", "period_end"])

    op.create_table(
        "reliability_report_layouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aircraft_family", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sections", JSONB(), nullable=False),
        sa.Column("page_settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "code", "revision", name="uq_rel_report_layout_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_rel_report_layout_revision"),
    )
    op.create_index("ix_rel_report_layout_active", "reliability_report_layouts", ["amo_id", "active", "aircraft_family"])

    op.create_table(
        "reliability_workbook_report_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("layout_id", sa.Integer(), sa.ForeignKey("reliability_report_layouts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("aircraft_filter", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rendered_data", JSONB(), nullable=False),
        sa.Column("rendered_html", sa.Text(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("generated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("period_end >= period_start", name="ck_rel_workbook_report_dates"),
    )
    op.create_index("ix_rel_workbook_report_period", "reliability_workbook_report_snapshots", ["amo_id", "period_start", "period_end"])
    op.create_index("ix_rel_workbook_report_layout", "reliability_workbook_report_snapshots", ["layout_id", "generated_at"])
    op.create_index("ix_reliability_workbook_report_snapshots_sha256_hash", "reliability_workbook_report_snapshots", ["sha256_hash"])


def downgrade() -> None:
    op.drop_table("reliability_workbook_report_snapshots")
    op.drop_table("reliability_report_layouts")
    op.drop_table("reliability_statistical_alert_results")
    op.drop_table("reliability_workbook_field_mappings")
    op.drop_table("reliability_workbook_records")
