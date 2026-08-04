"""add WinAir sync control

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-08-04 14:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6g7h8i9"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "winair_sync_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_config_id", sa.String(length=36), sa.ForeignKey("integration_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="SHADOW"),
        sa.Column("transport", sa.String(length=16), nullable=False, server_default="API"),
        sa.Column("direction", sa.String(length=24), nullable=False, server_default="BIDIRECTIONAL"),
        sa.Column("authority_json", sa.JSON(), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("dataset_config_json", sa.JSON(), nullable=False),
        sa.Column("last_cursor_json", sa.JSON(), nullable=False),
        sa.Column("hours_tolerance", sa.Numeric(14, 2), nullable=False, server_default="0.05"),
        sa.Column("cycles_tolerance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "name", name="uq_winair_profile_amo_name"),
        sa.UniqueConstraint("amo_id", "integration_config_id", name="uq_winair_profile_amo_config"),
        sa.CheckConstraint("hours_tolerance >= 0", name="ck_winair_profile_hours_tolerance"),
        sa.CheckConstraint("cycles_tolerance >= 0", name="ck_winair_profile_cycles_tolerance"),
    )
    op.create_index("ix_winair_profiles_amo_status", "winair_sync_profiles", ["amo_id", "status"])

    op.create_table(
        "winair_sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("requested_datasets_json", sa.JSON(), nullable=False),
        sa.Column("cursor_before_json", sa.JSON(), nullable=False),
        sa.Column("cursor_after_json", sa.JSON(), nullable=False),
        sa.Column("counts_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("triggered_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_winair_runs_amo_profile_started", "winair_sync_runs", ["amo_id", "profile_id", "started_at"])
    op.create_index("ix_winair_runs_amo_status", "winair_sync_runs", ["amo_id", "status"])

    op.create_table(
        "winair_sync_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("winair_sync_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=12), nullable=False),
        sa.Column("external_key", sa.String(length=160), nullable=False),
        sa.Column("local_object_type", sa.String(length=64), nullable=True),
        sa.Column("local_object_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="STAGED"),
        sa.Column("source_payload_json", sa.JSON(), nullable=False),
        sa.Column("normalized_payload_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("local_hash", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "dataset", "direction", "external_key", name="uq_winair_run_record"),
    )
    op.create_index("ix_winair_records_run_status", "winair_sync_records", ["run_id", "status"])
    op.create_index("ix_winair_records_profile_dataset", "winair_sync_records", ["profile_id", "dataset", "external_key"])

    op.create_table(
        "winair_object_maps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("external_key", sa.String(length=160), nullable=False),
        sa.Column("canonical_key", sa.String(length=160), nullable=True),
        sa.Column("local_object_type", sa.String(length=64), nullable=False),
        sa.Column("local_object_id", sa.String(length=64), nullable=False),
        sa.Column("last_source_hash", sa.String(length=64), nullable=True),
        sa.Column("last_local_hash", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "dataset", "external_key", name="uq_winair_object_map_external"),
    )
    op.create_index("ix_winair_maps_local", "winair_object_maps", ["amo_id", "local_object_type", "local_object_id"])

    op.create_table(
        "winair_sync_conflicts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("winair_sync_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("winair_sync_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_id", sa.String(length=36), sa.ForeignKey("winair_sync_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("external_key", sa.String(length=160), nullable=False),
        sa.Column("conflict_type", sa.String(length=48), nullable=False),
        sa.Column("source_payload_json", sa.JSON(), nullable=False),
        sa.Column("local_payload_json", sa.JSON(), nullable=False),
        sa.Column("field_differences_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="OPEN"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_winair_conflicts_amo_status", "winair_sync_conflicts", ["amo_id", "status"])
    op.create_index("ix_winair_conflicts_profile_dataset", "winair_sync_conflicts", ["profile_id", "dataset", "external_key"])


def downgrade() -> None:
    op.drop_index("ix_winair_conflicts_profile_dataset", table_name="winair_sync_conflicts")
    op.drop_index("ix_winair_conflicts_amo_status", table_name="winair_sync_conflicts")
    op.drop_table("winair_sync_conflicts")
    op.drop_index("ix_winair_maps_local", table_name="winair_object_maps")
    op.drop_table("winair_object_maps")
    op.drop_index("ix_winair_records_profile_dataset", table_name="winair_sync_records")
    op.drop_index("ix_winair_records_run_status", table_name="winair_sync_records")
    op.drop_table("winair_sync_records")
    op.drop_index("ix_winair_runs_amo_status", table_name="winair_sync_runs")
    op.drop_index("ix_winair_runs_amo_profile_started", table_name="winair_sync_runs")
    op.drop_table("winair_sync_runs")
    op.drop_index("ix_winair_profiles_amo_status", table_name="winair_sync_profiles")
    op.drop_table("winair_sync_profiles")
