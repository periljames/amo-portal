"""Add controlled procurement document evidence.

Revision ID: procurement_20260803_document_evidence
Revises: procurement_20260803_full_domain
"""

from alembic import op
import sqlalchemy as sa

revision = "procurement_20260803_document_evidence"
down_revision = "procurement_20260803_full_domain"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "procurement_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("document_kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="UPLOADED"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("physical_reference", sa.String(length=255), nullable=True),
        sa.Column("physical_location", sa.String(length=255), nullable=True),
        sa.Column("dms_document_id", sa.String(length=64), nullable=True),
        sa.Column("dms_revision_id", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uploaded_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_procurement_documents_entity", "procurement_documents", ["amo_id", "entity_type", "entity_id"])
    op.create_index("ix_procurement_documents_status", "procurement_documents", ["amo_id", "status", "created_at"])
    op.create_index("ix_procurement_documents_sha256", "procurement_documents", ["sha256"])
    op.create_index("ix_procurement_documents_dms_document_id", "procurement_documents", ["dms_document_id"])


def downgrade():
    op.drop_table("procurement_documents")
