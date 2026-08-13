"""Add governed Document Control retention/disposition ledger.

Revision ID: docctl_20260812_retention_disposition
Revises: docctl_20260812_reminder_deliveries
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "docctl_20260812_retention_disposition"
down_revision = "docctl_20260812_reminder_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_retention_dispositions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="DOCUMENT"),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("source_label", sa.String(length=255), nullable=False),
        sa.Column("retention_class", sa.String(length=64), nullable=False, server_default="STANDARD"),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("disposition_method", sa.String(length=64), nullable=True),
        sa.Column("certificate_evidence_asset_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("disposed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["certificate_evidence_asset_id"], ["document_evidence_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["disposed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manual_id", "source_type", "source_id", name="uq_document_retention_source"),
    )
    op.create_index("ix_document_retention_tenant_status", "document_retention_dispositions", ["tenant_id", "status", "retention_until"], unique=False)
    op.create_index("ix_document_retention_manual", "document_retention_dispositions", ["tenant_id", "manual_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_retention_manual", table_name="document_retention_dispositions")
    op.drop_index("ix_document_retention_tenant_status", table_name="document_retention_dispositions")
    op.drop_table("document_retention_dispositions")
