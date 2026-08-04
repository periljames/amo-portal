"""add migration control

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-08-04 15:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6g7h8i9j0"
down_revision = "d4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("preset", sa.String(length=64), nullable=True),
        sa.Column("target_aircraft_serial_number", sa.String(length=50), sa.ForeignKey("aircraft.serial_number", ondelete="SET NULL"), nullable=True),
        sa.Column("target_registration", sa.String(length=20), nullable=True),
        sa.Column("source_type", sa.String(length=24), nullable=False, server_default="SPREADSHEET"),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="DRY_RUN"),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("cutover_checklist_json", sa.JSON(), nullable=False),
        sa.Column("rollback_manifest_json", sa.JSON(), nullable=False),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "name", name="uq_migration_batch_amo_name"),
    )
    op.create_index("ix_migration_batches_amo_status", "migration_batches", ["amo_id", "status"])
    op.create_index("ix_migration_batches_aircraft", "migration_batches", ["amo_id", "target_aircraft_serial_number"])

    op.create_table(
        "migration_rows",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(length=36), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="STAGED"),
        sa.Column("action", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("local_object_type", sa.String(length=64), nullable=True),
        sa.Column("local_object_id", sa.String(length=64), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "dataset", "source_key", name="uq_migration_row_batch_source"),
        sa.UniqueConstraint("batch_id", "dataset", "source_row_number", name="uq_migration_row_batch_number"),
    )
    op.create_index("ix_migration_rows_batch_status", "migration_rows", ["batch_id", "status"])
    op.create_index("ix_migration_rows_batch_dataset", "migration_rows", ["batch_id", "dataset", "source_row_number"])

    op.create_table(
        "migration_reconciliation_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(length=36), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", sa.String(length=36), sa.ForeignKey("migration_rows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="ERROR"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("local_json", sa.JSON(), nullable=False),
        sa.Column("differences_json", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.String(length=24), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_migration_recon_batch_status", "migration_reconciliation_items", ["batch_id", "status"])
    op.create_index("ix_migration_recon_amo_severity", "migration_reconciliation_items", ["amo_id", "severity", "status"])

    op.create_table(
        "migration_checkpoints",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(length=36), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checkpoint_key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "checkpoint_key", name="uq_migration_checkpoint_key"),
    )
    op.create_index("ix_migration_checkpoints_batch_status", "migration_checkpoints", ["batch_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_migration_checkpoints_batch_status", table_name="migration_checkpoints")
    op.drop_table("migration_checkpoints")
    op.drop_index("ix_migration_recon_amo_severity", table_name="migration_reconciliation_items")
    op.drop_index("ix_migration_recon_batch_status", table_name="migration_reconciliation_items")
    op.drop_table("migration_reconciliation_items")
    op.drop_index("ix_migration_rows_batch_dataset", table_name="migration_rows")
    op.drop_index("ix_migration_rows_batch_status", table_name="migration_rows")
    op.drop_table("migration_rows")
    op.drop_index("ix_migration_batches_aircraft", table_name="migration_batches")
    op.drop_index("ix_migration_batches_amo_status", table_name="migration_batches")
    op.drop_table("migration_batches")
