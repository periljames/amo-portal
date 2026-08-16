"""Add governed pre-audit guest document submissions.

Revision ID: quality_260816_guest_documents
Revises: quality_260816_external_access
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_guest_documents"
down_revision = "quality_260816_external_access"
branch_labels = None
depends_on = None

TABLE = "quality_audit_document_submissions"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("document_request_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=24), server_default="UPLOAD", nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("response_comment", sa.Text(), nullable=True),
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('UPLOAD')", name="ck_quality_audit_document_submission_source"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_quality_audit_document_submission_size"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_request_id"], ["quality_audit_document_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_audit_document_submission_request",
        TABLE,
        ["amo_id", "audit_id", "document_request_id", "created_at"],
    )
    op.create_index(
        "ix_quality_audit_document_submission_hash",
        TABLE,
        ["amo_id", "sha256"],
    )

    if _is_postgresql():
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"""
            CREATE POLICY {TABLE}_amo_isolation
            ON "{TABLE}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_document_submission_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Quality audit document submission history is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_{TABLE}_append_only
            BEFORE UPDATE OR DELETE ON {TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_document_submission_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_append_only ON {TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_document_submission_mutation()"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_amo_isolation ON \"{TABLE}\""))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_document_submission_hash", table_name=TABLE)
    op.drop_index("ix_quality_audit_document_submission_request", table_name=TABLE)
    op.drop_table(TABLE)
