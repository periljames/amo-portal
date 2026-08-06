"""add rollout and spreadsheet retirement

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-08-04 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rollout_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("selection_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "name", name="uq_rollout_group_amo_name"),
    )
    op.create_index("ix_rollout_groups_amo_status", "rollout_groups", ["amo_id", "status"])

    op.create_table(
        "rollout_waves",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(length=36), sa.ForeignKey("rollout_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PLANNED"),
        sa.Column("readiness_json", sa.JSON(), nullable=False),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", "sequence_no", name="uq_rollout_wave_sequence"),
        sa.UniqueConstraint("group_id", "name", name="uq_rollout_wave_name"),
        sa.CheckConstraint("sequence_no >= 1", name="ck_rollout_wave_sequence"),
        sa.CheckConstraint("planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start", name="ck_rollout_wave_dates"),
    )
    op.create_index("ix_rollout_waves_amo_status", "rollout_waves", ["amo_id", "status"])
    op.create_index("ix_rollout_waves_group", "rollout_waves", ["group_id", "sequence_no"])

    op.create_table(
        "rollout_wave_aircraft",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wave_id", sa.String(length=36), sa.ForeignKey("rollout_waves.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("registration", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PLANNED"),
        sa.Column("migration_batch_id", sa.String(length=36), sa.ForeignKey("migration_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dual_run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cutover_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wave_id", "aircraft_serial_number", name="uq_rollout_wave_aircraft"),
    )
    op.create_index("ix_rollout_wave_aircraft_status", "wave_id", ["status"])
    op.create_index("ix_rollout_aircraft_amo_registration", "rollout_wave_aircraft", ["amo_id", "registration"])

    op.create_table(
        "rollout_checklist_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wave_id", sa.String(length=36), sa.ForeignKey("rollout_waves.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=True),
        sa.Column("check_key", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wave_id", "aircraft_serial_number", "check_key", name="uq_rollout_checklist_scope_key"),
    )
    op.create_index("ix_rollout_checklist_wave_status", "rollout_checklist_items", ["wave_id", "status"])
    op.create_index("ix_rollout_checklist_aircraft", "rollout_checklist_items", ["aircraft_serial_number", "status"])

    op.create_table(
        "spreadsheet_register",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("data_domain", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="LIVE"),
        sa.Column("replacement_route", sa.String(length=255), nullable=True),
        sa.Column("retirement_criteria_json", sa.JSON(), nullable=False),
        sa.Column("retirement_evidence_json", sa.JSON(), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "name", name="uq_spreadsheet_register_amo_name"),
    )
    op.create_index("ix_spreadsheet_register_amo_status", "spreadsheet_register", ["amo_id", "status"])
    op.create_index("ix_spreadsheet_register_domain", "spreadsheet_register", ["amo_id", "data_domain"])

    op.create_table(
        "spreadsheet_retirement_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spreadsheet_id", sa.String(length=36), sa.ForeignKey("spreadsheet_register.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_spreadsheet_events_sheet_time", "spreadsheet_retirement_events", ["spreadsheet_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_spreadsheet_events_sheet_time", table_name="spreadsheet_retirement_events")
    op.drop_table("spreadsheet_retirement_events")
    op.drop_index("ix_spreadsheet_register_domain", table_name="spreadsheet_register")
    op.drop_index("ix_spreadsheet_register_amo_status", table_name="spreadsheet_register")
    op.drop_table("spreadsheet_register")
    op.drop_index("ix_rollout_checklist_aircraft", table_name="rollout_checklist_items")
    op.drop_index("ix_rollout_checklist_wave_status", table_name="rollout_checklist_items")
    op.drop_table("rollout_checklist_items")
    op.drop_index("ix_rollout_aircraft_amo_registration", table_name="rollout_wave_aircraft")
    op.drop_index("ix_rollout_wave_aircraft_status", table_name="rollout_wave_aircraft")
    op.drop_table("rollout_wave_aircraft")
    op.drop_index("ix_rollout_waves_group", table_name="rollout_waves")
    op.drop_index("ix_rollout_waves_amo_status", table_name="rollout_waves")
    op.drop_table("rollout_waves")
    op.drop_index("ix_rollout_groups_amo_status", table_name="rollout_groups")
    op.drop_table("rollout_groups")
