"""Add governed Reliability workbook import batches and row results.

Revision ID: rel_20260806_workbook_imports
Revises: rel_20260806_workbook_main_merge
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "rel_20260806_workbook_imports"
down_revision: Union[str, Sequence[str], None] = "rel_20260806_workbook_main_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reliability_workbook_import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("dataset_code", sa.String(length=24), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("sanitized_filename", sa.String(length=255), nullable=False),
        sa.Column("file_extension", sa.String(length=8), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detected_sheets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_sheet", sa.String(length=128), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False),
        sa.Column("header_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("file_size_bytes > 0", name="ck_rel_workbook_import_size_positive"),
        sa.CheckConstraint("header_row > 0", name="ck_rel_workbook_import_header_positive"),
        sa.CheckConstraint("status IN ('PREVIEW_READY','PROCESSING','COMPLETED','PARTIAL_FAILED','FAILED')", name="ck_rel_workbook_import_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "profile_code", "dataset_code", "selected_sheet", "source_hash", name="uq_rel_workbook_import_source"),
    )
    op.create_index("ix_rel_workbook_import_scope", "reliability_workbook_import_batches", ["amo_id", "status", "created_at"], unique=False)
    op.create_index("ix_rel_workbook_import_hash", "reliability_workbook_import_batches", ["amo_id", "source_hash"], unique=False)

    op.create_table(
        "reliability_workbook_import_row_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("row_source_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mapped_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("workbook_record_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_number > 0", name="ck_rel_workbook_import_row_positive"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_rel_workbook_import_attempt_nonnegative"),
        sa.CheckConstraint("status IN ('VALID','INVALID','COMMITTED','FAILED')", name="ck_rel_workbook_import_row_status"),
        sa.ForeignKeyConstraint(["batch_id"], ["reliability_workbook_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workbook_record_id"], ["reliability_workbook_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_rel_workbook_import_row"),
    )
    op.create_index("ix_rel_workbook_import_row_queue", "reliability_workbook_import_row_results", ["batch_id", "status", "row_number"], unique=False)
    op.create_index("ix_rel_workbook_import_row_hash", "reliability_workbook_import_row_results", ["row_source_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rel_workbook_import_row_hash", table_name="reliability_workbook_import_row_results")
    op.drop_index("ix_rel_workbook_import_row_queue", table_name="reliability_workbook_import_row_results")
    op.drop_table("reliability_workbook_import_row_results")
    op.drop_index("ix_rel_workbook_import_hash", table_name="reliability_workbook_import_batches")
    op.drop_index("ix_rel_workbook_import_scope", table_name="reliability_workbook_import_batches")
    op.drop_table("reliability_workbook_import_batches")
