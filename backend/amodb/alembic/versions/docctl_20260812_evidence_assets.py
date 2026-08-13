"""Add immutable governed Document Control evidence assets.

Revision ID: docctl_20260812_evidence_assets
Revises: quality_260811_car_loop
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "docctl_20260812_evidence_assets"
down_revision = "quality_260811_car_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_evidence_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=48), nullable=False, server_default="GENERAL"),
        sa.Column("purpose", sa.String(length=128), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("source_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_evidence_tenant_manual_created",
        "document_evidence_assets",
        ["tenant_id", "manual_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_evidence_tenant_revision",
        "document_evidence_assets",
        ["tenant_id", "revision_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_evidence_tenant_sha256",
        "document_evidence_assets",
        ["tenant_id", "sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_evidence_tenant_sha256", table_name="document_evidence_assets")
    op.drop_index("ix_document_evidence_tenant_revision", table_name="document_evidence_assets")
    op.drop_index("ix_document_evidence_tenant_manual_created", table_name="document_evidence_assets")
    op.drop_table("document_evidence_assets")
