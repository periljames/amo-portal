"""Bridge audit preparation to the canonical Document Control repository.

Revision ID: quality_260817_canonical_document_bridge
Revises: quality_260817_occurrence_frontend_completion
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260817_canonical_document_bridge"
down_revision = "quality_260817_occurrence_frontend_completion"
branch_labels = None
depends_on = None

DOC_META = "quality_audit_document_request_metadata"
CANONICAL_LINK = "quality_audit_canonical_document_submissions"


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
    op.execute(sa.text(f'DROP POLICY IF EXISTS {table}_amo_isolation ON "{table}"'))
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    # Preserve the existing QMS-local UUID references and add an explicit,
    # separately typed bridge to the portal-wide Document Control repository.
    op.add_column(
        DOC_META,
        sa.Column(
            "controlled_source_system",
            sa.String(length=32),
            nullable=False,
            server_default="QMS_LOCAL",
        ),
    )
    op.add_column(DOC_META, sa.Column("canonical_document_id", sa.String(length=36), nullable=True))
    op.add_column(DOC_META, sa.Column("canonical_revision_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_q_audit_doc_meta_dc_doc",
        DOC_META,
        "manuals",
        ["canonical_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_q_audit_doc_meta_dc_rev",
        DOC_META,
        "manual_revisions",
        ["canonical_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_q_audit_doc_meta_source_system",
        DOC_META,
        "controlled_source_system IN ('QMS_LOCAL','DOCUMENT_CONTROL')",
    )
    op.create_check_constraint(
        "ck_q_audit_doc_meta_canonical_pair",
        DOC_META,
        "canonical_revision_id IS NULL OR canonical_document_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_q_audit_doc_meta_identity",
        DOC_META,
        """
        (
            controlled_source_system = 'QMS_LOCAL'
            AND canonical_document_id IS NULL
            AND canonical_revision_id IS NULL
        )
        OR
        (
            controlled_source_system = 'DOCUMENT_CONTROL'
            AND controlled_document_id IS NULL
            AND controlled_revision_id IS NULL
        )
        """,
    )
    op.create_index(
        "ix_q_audit_doc_meta_dc_ref",
        DOC_META,
        ["amo_id", "canonical_document_id", "canonical_revision_id"],
    )

    # Canonical submissions are intentionally separate from the existing
    # qms_documents-backed UUID table. No existing FK or nullability contract is
    # weakened to accommodate Document Control's string identities.
    op.create_table(
        CANONICAL_LINK,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("response_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["quality_audit_document_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["manuals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_q_audit_canonical_link_request",
        CANONICAL_LINK,
        ["amo_id", "audit_id", "request_id", "created_at"],
    )
    _enable_rls(CANONICAL_LINK)


def downgrade() -> None:
    _disable_rls(CANONICAL_LINK)
    op.drop_index("ix_q_audit_canonical_link_request", table_name=CANONICAL_LINK)
    op.drop_table(CANONICAL_LINK)

    op.drop_index("ix_q_audit_doc_meta_dc_ref", table_name=DOC_META)
    op.drop_constraint("ck_q_audit_doc_meta_identity", DOC_META, type_="check")
    op.drop_constraint("ck_q_audit_doc_meta_canonical_pair", DOC_META, type_="check")
    op.drop_constraint("ck_q_audit_doc_meta_source_system", DOC_META, type_="check")
    op.drop_constraint("fk_q_audit_doc_meta_dc_rev", DOC_META, type_="foreignkey")
    op.drop_constraint("fk_q_audit_doc_meta_dc_doc", DOC_META, type_="foreignkey")
    op.drop_column(DOC_META, "canonical_revision_id")
    op.drop_column(DOC_META, "canonical_document_id")
    op.drop_column(DOC_META, "controlled_source_system")
