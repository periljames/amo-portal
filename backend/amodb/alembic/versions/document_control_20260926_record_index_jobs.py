"""Durable asynchronous extraction queue for retained records.

Revision ID: docctl_260926_record_index
Revises: docctl_260926_knowledge_wh
"""
from alembic import op
import sqlalchemy as sa

revision = "docctl_260926_record_index"
down_revision = "docctl_260926_knowledge_wh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_record_index_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_asset_id", sa.String(length=36), sa.ForeignKey("document_record_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "record_asset_id", name="uq_document_record_index_asset"),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','READY','FAILED')", name="ck_document_record_index_status"),
    )
    op.create_index("ix_document_record_index_pending", "document_record_index_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_document_record_index_pending", table_name="document_record_index_jobs")
    op.drop_table("document_record_index_jobs")
