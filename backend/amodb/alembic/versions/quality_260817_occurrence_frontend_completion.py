"""Complete audit occurrence collaboration and preparation metadata.

Revision ID: quality_260817_occurrence_frontend_completion
Revises: quality_260817_audit_presence
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260817_occurrence_frontend_completion"
down_revision = "quality_260817_audit_presence"
branch_labels = None
depends_on = None

DOC_META = "quality_audit_document_request_metadata"
MEETING = "quality_audit_meetings"
NARRATIVE = "quality_audit_closing_narratives"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    if not _is_postgresql():
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {table}_amo_isolation
        ON "{table}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table: str) -> None:
    if not _is_postgresql():
        return
    op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_amo_isolation ON \"{table}\""))
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        DOC_META,
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("request_type", sa.String(length=64), nullable=False, server_default="DOCUMENT"),
        sa.Column("linked_criterion", sa.Text(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_mode", sa.String(length=32), nullable=False, server_default="UPLOAD_OR_CONTROLLED"),
        sa.Column("controlled_document_id", sa.Uuid(), nullable=True),
        sa.Column("controlled_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["quality_audit_document_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["controlled_document_id"], ["qms_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["controlled_revision_id"], ["qms_document_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("request_id"),
        sa.CheckConstraint("request_type IN ('DOCUMENT','RECORD','MANUAL','FORM','CERTIFICATE','REGISTER','OTHER')", name="ck_quality_audit_doc_meta_type"),
        sa.CheckConstraint("source_mode IN ('UPLOAD','CONTROLLED_DMS','UPLOAD_OR_CONTROLLED')", name="ck_quality_audit_doc_meta_source"),
        sa.CheckConstraint("controlled_revision_id IS NULL OR controlled_document_id IS NOT NULL", name="ck_quality_audit_doc_meta_revision_document"),
    )
    op.create_index("ix_quality_audit_doc_meta_audit", DOC_META, ["amo_id", "audit_id"])
    _enable_rls(DOC_META)

    op.create_table(
        MEETING,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("meeting_type", sa.String(length=24), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("conference_url", sa.String(length=1024), nullable=True),
        sa.Column("agenda", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PLANNED"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("meeting_type IN ('OPENING','CLOSING','FOLLOW_UP','OTHER')", name="ck_quality_audit_meeting_type"),
        sa.CheckConstraint("status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')", name="ck_quality_audit_meeting_status"),
        sa.CheckConstraint("scheduled_end IS NULL OR scheduled_end >= scheduled_start", name="ck_quality_audit_meeting_dates"),
    )
    op.create_index("ix_quality_audit_meeting_audit", MEETING, ["amo_id", "audit_id", "scheduled_start"])
    _enable_rls(MEETING)

    op.create_table(
        NARRATIVE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("positive_practices", sa.Text(), nullable=True),
        sa.Column("management_summary", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", name="uq_quality_audit_closing_narrative"),
    )
    op.create_index("ix_quality_audit_closing_narrative_audit", NARRATIVE, ["amo_id", "audit_id"])
    _enable_rls(NARRATIVE)


def downgrade() -> None:
    for table in (NARRATIVE, MEETING, DOC_META):
        _disable_rls(table)
    op.drop_index("ix_quality_audit_closing_narrative_audit", table_name=NARRATIVE)
    op.drop_table(NARRATIVE)
    op.drop_index("ix_quality_audit_meeting_audit", table_name=MEETING)
    op.drop_table(MEETING)
    op.drop_index("ix_quality_audit_doc_meta_audit", table_name=DOC_META)
    op.drop_table(DOC_META)
