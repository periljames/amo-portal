"""add technical records module

Revision ID: t9r8e7c6h5n4
Revises: k1b2c3d4e5f6
Create Date: 2026-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "t9r8e7c6h5n4"
down_revision = "k1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technical_record_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("utilisation_manual_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ad_sb_use_hours_cycles", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("record_retention_years", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("allow_manual_maintenance_records", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id"),
    )
    op.create_index(op.f("ix_technical_record_settings_amo_id"), "technical_record_settings", ["amo_id"], unique=True)

    op.create_table(
        "technical_aircraft_utilisation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("tail_id", sa.String(length=50), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("cycles", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("conflict_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("hours >= 0", name="ck_tr_util_hours_nonneg"),
        sa.CheckConstraint("cycles >= 0", name="ck_tr_util_cycles_nonneg"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tail_id"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tr_util_amo_tail_date", "technical_aircraft_utilisation", ["amo_id", "tail_id", "entry_date"], unique=False)

    op.create_table(
        "technical_logbook_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("tail_id", sa.String(length=50), nullable=False),
        sa.Column("log_type", sa.String(length=16), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("linked_wo_id", sa.Integer(), nullable=True),
        sa.Column("linked_crs_id", sa.Integer(), nullable=True),
        sa.Column("evidence_asset_ids", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tail_id"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_wo_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_crs_id"], ["crs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tr_logbook_amo_tail_date", "technical_logbook_entries", ["amo_id", "tail_id", "entry_date"], unique=False)

    op.create_table(
        "technical_deferrals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("tail_id", sa.String(length=50), nullable=False),
        sa.Column("defect_ref", sa.String(length=64), nullable=False),
        sa.Column("deferral_type", sa.String(length=32), nullable=False),
        sa.Column("deferred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("linked_wo_id", sa.Integer(), nullable=True),
        sa.Column("linked_crs_id", sa.Integer(), nullable=True),
        sa.Column("extension_history_json", sa.JSON(), nullable=False),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tail_id"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_wo_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_crs_id"], ["crs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tr_deferrals_amo_expiry", "technical_deferrals", ["amo_id", "expiry_at"], unique=False)

    op.create_table(
        "technical_maintenance_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("tail_id", sa.String(length=50), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference_data_text", sa.Text(), nullable=False),
        sa.Column("certifying_user_id", sa.String(length=36), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("linked_wo_id", sa.Integer(), nullable=True),
        sa.Column("linked_wp_id", sa.String(length=64), nullable=True),
        sa.Column("evidence_asset_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tail_id"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["certifying_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_wo_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tr_maint_records_amo_tail_date", "technical_maintenance_records", ["amo_id", "tail_id", "performed_at"], unique=False)

    op.create_table(
        "technical_airworthiness_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.String(length=4), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("applicability_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("next_due_hours", sa.Float(), nullable=True),
        sa.Column("next_due_cycles", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "item_type", "reference", name="uq_tr_airworthiness_ref"),
    )
    op.create_index("ix_tr_airworthiness_type_status", "technical_airworthiness_items", ["amo_id", "item_type", "status"], unique=False)

    op.create_table(
        "technical_airworthiness_compliance_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("tail_id", sa.String(length=50), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method_text", sa.Text(), nullable=False),
        sa.Column("linked_wo_id", sa.Integer(), nullable=True),
        sa.Column("evidence_asset_ids", sa.JSON(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("next_due_hours", sa.Float(), nullable=True),
        sa.Column("next_due_cycles", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["technical_airworthiness_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tail_id"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["component_id"], ["aircraft_components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_wo_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tr_airworthiness_events_item", "technical_airworthiness_compliance_events", ["amo_id", "item_id", "performed_at"], unique=False)

    op.create_table(
        "technical_exception_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("ex_type", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="Open"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tr_exception_queue_amo_status", "technical_exception_queue", ["amo_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tr_exception_queue_amo_status", table_name="technical_exception_queue")
    op.drop_table("technical_exception_queue")
    op.drop_index("ix_tr_airworthiness_events_item", table_name="technical_airworthiness_compliance_events")
    op.drop_table("technical_airworthiness_compliance_events")
    op.drop_index("ix_tr_airworthiness_type_status", table_name="technical_airworthiness_items")
    op.drop_table("technical_airworthiness_items")
    op.drop_index("ix_tr_maint_records_amo_tail_date", table_name="technical_maintenance_records")
    op.drop_table("technical_maintenance_records")
    op.drop_index("ix_tr_deferrals_amo_expiry", table_name="technical_deferrals")
    op.drop_table("technical_deferrals")
    op.drop_index("ix_tr_logbook_amo_tail_date", table_name="technical_logbook_entries")
    op.drop_table("technical_logbook_entries")
    op.drop_index("ix_tr_util_amo_tail_date", table_name="technical_aircraft_utilisation")
    op.drop_table("technical_aircraft_utilisation")
    op.drop_index(op.f("ix_technical_record_settings_amo_id"), table_name="technical_record_settings")
    op.drop_table("technical_record_settings")
