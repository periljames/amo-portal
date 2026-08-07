"""Add reader evidence snapshots and annotation migration review.

Revision ID: docgov_20260807_reader_governance
Revises: docgov_merge_20260807
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "docgov_20260807_reader_governance"
down_revision: Union[str, Sequence[str], None] = "docgov_merge_20260807"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "document_annotation_migrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("source_annotation_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("target_revision_id", sa.String(length=36), nullable=False),
        sa.Column("proposed_location_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("migration_strategy", sa.String(length=32), nullable=False),
        sa.Column("confidence_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("target_annotation_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("confidence_percent >= 0 AND confidence_percent <= 100", name="ck_doc_annotation_migration_confidence"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_annotation_id"], ["document_annotations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_annotation_id"], ["document_annotations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "source_annotation_id", "target_revision_id", name="uq_doc_annotation_migration_target"),
    )
    op.create_index("ix_doc_annotation_migration_review", "document_annotation_migrations", ["tenant_id", "status", "target_revision_id"])
    op.create_index("ix_doc_annotation_migration_source", "document_annotation_migrations", ["source_annotation_id", "source_revision_id"])

    op.create_table(
        "document_evidence_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "snapshot_sha256", name="uq_doc_evidence_snapshot_sha"),
    )
    op.create_index("ix_doc_evidence_revision_created", "document_evidence_snapshots", ["tenant_id", "revision_id", "created_at"])
    op.create_index("ix_doc_evidence_manual_created", "document_evidence_snapshots", ["tenant_id", "manual_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_doc_evidence_manual_created", table_name="document_evidence_snapshots")
    op.drop_index("ix_doc_evidence_revision_created", table_name="document_evidence_snapshots")
    op.drop_table("document_evidence_snapshots")
    op.drop_index("ix_doc_annotation_migration_source", table_name="document_annotation_migrations")
    op.drop_index("ix_doc_annotation_migration_review", table_name="document_annotation_migrations")
    op.drop_table("document_annotation_migrations")
