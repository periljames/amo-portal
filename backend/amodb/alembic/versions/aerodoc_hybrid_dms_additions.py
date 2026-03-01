"""add aerodoc hybrid dms columns and physical copy tables

Revision ID: aerodoc_hybrid_dms
Revises: d0c1b2a3e4f5, t9r8e7c6h5n4
Create Date: 2026-03-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "aerodoc_hybrid_dms"
down_revision = ("d0c1b2a3e4f5", "t9r8e7c6h5n4")
branch_labels = None
depends_on = None


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector, table: str, name: str) -> bool:
    return any(col["name"] == name for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "qms_documents"):
        if not _has_column(inspector, "qms_documents", "security_level"):
            op.add_column("qms_documents", sa.Column("security_level", sa.String(length=32), nullable=True))
            op.execute("UPDATE qms_documents SET security_level='INTERNAL' WHERE security_level IS NULL")
            op.alter_column("qms_documents", "security_level", nullable=False)
        if not _has_column(inspector, "qms_documents", "retention_category"):
            op.add_column("qms_documents", sa.Column("retention_category", sa.String(length=32), nullable=True))
            op.execute("UPDATE qms_documents SET retention_category='MAINT_RECORD_5Y' WHERE retention_category IS NULL")
            op.alter_column("qms_documents", "retention_category", nullable=False)
        if not _has_column(inspector, "qms_documents", "owner_user_id"):
            op.add_column("qms_documents", sa.Column("owner_user_id", sa.String(length=36), nullable=True))

    if _has_table(inspector, "qms_document_revisions"):
        additions = [
            ("version_semver", sa.String(length=32)),
            ("lifecycle_status", sa.String(length=32)),
            ("sha256", sa.String(length=64)),
            ("primary_storage_provider", sa.String(length=32)),
            ("primary_storage_key", sa.String(length=1024)),
            ("primary_storage_etag", sa.String(length=128)),
            ("byte_size", sa.Integer()),
            ("mime_type", sa.String(length=255)),
            ("superseded_at", sa.DateTime(timezone=True)),
            ("obsolete_at", sa.DateTime(timezone=True)),
        ]
        for column_name, column_type in additions:
            if not _has_column(inspector, "qms_document_revisions", column_name):
                op.add_column("qms_document_revisions", sa.Column(column_name, column_type, nullable=True))
        if _has_column(inspector, "qms_document_revisions", "lifecycle_status"):
            op.execute("UPDATE qms_document_revisions SET lifecycle_status='DRAFT' WHERE lifecycle_status IS NULL")

    inspector = inspect(bind)
    if not _has_table(inspector, "physical_controlled_copies"):
        op.create_table(
            "physical_controlled_copies",
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("digital_revision_id", sa.UUID(), sa.ForeignKey("qms_document_revisions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("copy_serial_number", sa.String(length=128), nullable=False),
            sa.Column("current_holder_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("storage_location_path", sa.String(length=512), nullable=True),
            sa.Column("last_inspected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
            sa.Column("is_controlled_copy", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("copy_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_copy_id", sa.UUID(), sa.ForeignKey("physical_controlled_copies.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("amo_id", "copy_serial_number", name="uq_physical_controlled_copy_serial"),
        )
        op.create_index("ix_physical_copy_amo_revision", "physical_controlled_copies", ["amo_id", "digital_revision_id"])

    inspector = inspect(bind)
    if not _has_table(inspector, "custody_logs"):
        op.create_table(
            "custody_logs",
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("physical_copy_id", sa.UUID(), sa.ForeignKey("physical_controlled_copies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("gps_lat", sa.Numeric(10, 7), nullable=True),
            sa.Column("gps_lng", sa.Numeric(10, 7), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        )
        op.create_index("ix_custody_logs_amo_copy_occurred", "custody_logs", ["amo_id", "physical_copy_id", "occurred_at"])


def downgrade() -> None:
    # Production-safe downgrade: keep additive columns and tables to avoid destructive data loss.
    # Manual rollback must restore pre-migration DB backup if full revert is required.
    pass
