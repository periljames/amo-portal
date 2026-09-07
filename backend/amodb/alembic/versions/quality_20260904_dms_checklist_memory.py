"""Connect canonical DMS checklists to reusable audit preparation memory.

Revision ID: quality_260904_dms_memory
Revises: quality_260904_notice_pdf
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260904_dms_memory"
down_revision = "quality_260904_notice_pdf"
branch_labels = None
depends_on = None


TABLE = "quality_audit_checklist_memory"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        "quality_audit_checklist_templates",
        sa.Column("canonical_document_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_quality_checklist_template_canonical_document",
        "quality_audit_checklist_templates",
        "manuals",
        ["canonical_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_quality_audit_checklist_templates_canonical_document_id",
        "quality_audit_checklist_templates",
        ["canonical_document_id"],
    )

    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("context_key", sa.String(length=255), nullable=False),
        sa.Column("selection_key", sa.String(length=96), nullable=False),
        sa.Column("audit_scope_code", sa.String(length=32), nullable=True),
        sa.Column("audit_kind", sa.String(length=32), nullable=True),
        sa.Column("auditee_key", sa.String(length=255), nullable=True),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_document_id", sa.String(length=36), nullable=True),
        sa.Column("last_audit_id", sa.Uuid(), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["quality_audit_checklist_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_document_id"], ["manuals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_audit_id"], ["qms_audits.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "context_key", "selection_key", name="uq_quality_audit_checklist_memory_selection"),
    )
    op.create_index("ix_quality_audit_checklist_memory_context", TABLE, ["amo_id", "context_key", "last_used_at"])

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
    op.drop_index("ix_quality_audit_checklist_memory_context", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_index("ix_quality_audit_checklist_templates_canonical_document_id", table_name="quality_audit_checklist_templates")
    op.drop_constraint("fk_quality_checklist_template_canonical_document", "quality_audit_checklist_templates", type_="foreignkey")
    op.drop_column("quality_audit_checklist_templates", "canonical_document_id")
