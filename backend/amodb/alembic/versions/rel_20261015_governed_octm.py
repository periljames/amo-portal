"""Add governed engine oil-consumption monitoring.

Revision ID: rel_261015_octm_governed
Revises: quality_261003_evidence_context
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "rel_261015_octm_governed"
down_revision = "quality_261003_evidence_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reliability_octm_source_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), nullable=False),
        sa.Column("techsheet_ref", sa.String(160), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_uri", sa.String(2048), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_octm_source_asset_page", "reliability_octm_source_assets",
                    ["amo_id", "aircraft_serial_number", "techsheet_ref"])
    op.create_index("ix_octm_source_asset_checksum", "reliability_octm_source_assets", ["amo_id", "sha256"])
    op.create_table(
        "reliability_octm_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_position", sa.String(32), nullable=False),
        sa.Column("engine_serial_number", sa.String(100), nullable=False),
        sa.Column("installation_ref", sa.String(120), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("techsheet_ref", sa.String(160), nullable=False),
        sa.Column("sector_ref", sa.String(100)),
        sa.Column("source_scope", sa.String(20), nullable=False, server_default="SECTOR"),
        sa.Column("source_context", sa.JSON()),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("external_record_id", sa.String(180)),
        sa.Column("source_evidence_ref", sa.String(512)),
        sa.Column("maintenance_complete", sa.String(24), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("oil_quantity", sa.Float()),
        sa.Column("oil_unit", sa.String(16)),
        sa.Column("oil_specification", sa.String(100)),
        sa.Column("reference_method", sa.String(120)),
        sa.Column("reference_level", sa.String(120)),
        sa.Column("engine_counter_hours", sa.Float()),
        sa.Column("flight_hours", sa.Float()),
        sa.Column("remarks", sa.Text()),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("review_note", sa.Text()),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_changed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "aircraft_serial_number", "techsheet_ref", "engine_serial_number", "event_sequence", name="uq_octm_source_event"),
        sa.UniqueConstraint("amo_id", "aircraft_serial_number", "techsheet_ref", "engine_position", "event_sequence", name="uq_octm_source_engine_position"),
    )
    op.create_index("ix_octm_engine_date", "reliability_octm_entries", ["amo_id", "engine_serial_number", "installation_ref", "event_date"])
    op.create_index("ix_octm_queue", "reliability_octm_entries", ["amo_id", "review_status"])
    op.create_index("ix_reliability_octm_entries_amo_id", "reliability_octm_entries", ["amo_id"])
    op.create_table(
        "reliability_octm_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("reliability_octm_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=False),
        sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reliability_octm_revisions_amo_id", "reliability_octm_revisions", ["amo_id"])
    op.create_index("ix_reliability_octm_revisions_entry_id", "reliability_octm_revisions", ["entry_id"])
    op.create_table(
        "reliability_octm_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_serial_number", sa.String(100), nullable=False),
        sa.Column("installation_ref", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("engine_model", sa.String(120), nullable=False),
        sa.Column("limit_qt_per_fh", sa.Float(), nullable=False),
        sa.Column("alert_increase_percent", sa.Float()),
        sa.Column("technical_data_ref", sa.String(200), nullable=False),
        sa.Column("technical_data_revision", sa.String(100), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "engine_serial_number", "installation_ref", "version", name="uq_octm_profile_version"),
    )
    op.create_index("ix_octm_profile_effective", "reliability_octm_profiles", ["amo_id", "engine_serial_number", "installation_ref", "effective_from"])
    op.create_index("ix_reliability_octm_profiles_amo_id", "reliability_octm_profiles", ["amo_id"])


def downgrade():
    op.drop_table("reliability_octm_profiles")
    op.drop_table("reliability_octm_revisions")
    op.drop_table("reliability_octm_entries")
    op.drop_table("reliability_octm_source_assets")
