"""P0 training record integrity fields

Revision ID: p0a6_train_record
Revises: p0a5_train_plan
Create Date: 2026-04-09 00:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p0a6_train_record"
down_revision = "p0a5_train_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("training_records", sa.Column("legacy_record_id", sa.String(length=64), nullable=True))
    op.add_column("training_records", sa.Column("source_status", sa.String(length=64), nullable=True))
    op.add_column("training_records", sa.Column("record_status", sa.String(length=64), nullable=True))
    op.add_column("training_records", sa.Column("superseded_by_record_id", sa.String(length=36), nullable=True))
    op.add_column("training_records", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("training_records", sa.Column("purge_after", sa.Date(), nullable=True))
    op.create_foreign_key(
        "fk_training_records_superseded_by",
        "training_records",
        "training_records",
        ["superseded_by_record_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_training_records_amo_status", "training_records", ["amo_id", "record_status"])
    op.create_index("idx_training_records_purge_after", "training_records", ["purge_after"])


def downgrade() -> None:
    op.drop_index("idx_training_records_purge_after", table_name="training_records")
    op.drop_index("idx_training_records_amo_status", table_name="training_records")
    op.drop_constraint("fk_training_records_superseded_by", "training_records", type_="foreignkey")
    op.drop_column("training_records", "purge_after")
    op.drop_column("training_records", "superseded_at")
    op.drop_column("training_records", "superseded_by_record_id")
    op.drop_column("training_records", "record_status")
    op.drop_column("training_records", "source_status")
    op.drop_column("training_records", "legacy_record_id")
