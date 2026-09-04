"""Add controlled PDF artifacts for audit notice preview and delivery.

Revision ID: quality_260904_notice_pdf
Revises: audit_260903_corr_255
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260904_notice_pdf"
down_revision = "audit_260903_corr_255"
branch_labels = None
depends_on = None


TABLE = "quality_audit_notice_artifacts"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), server_default="application/pdf", nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("signed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("signed_by_name", sa.String(length=255), nullable=True),
        sa.Column("signed_by_title", sa.String(length=255), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('GENERATED','UPLOADED')", name="ck_quality_audit_notice_artifact_source"),
        sa.CheckConstraint("size_bytes > 0", name="ck_quality_audit_notice_artifact_size"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_id"], ["quality_audit_notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notice_id", name="uq_quality_audit_notice_artifact_notice"),
    )
    op.create_index(
        "ix_quality_audit_notice_artifact_audit",
        TABLE,
        ["amo_id", "audit_id", "created_at"],
    )

    if _is_postgresql():
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"""
            CREATE POLICY {TABLE}_amo_isolation ON "{TABLE}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f'DROP POLICY IF EXISTS {TABLE}_amo_isolation ON "{TABLE}"'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_notice_artifact_audit", table_name=TABLE)
    op.drop_table(TABLE)

