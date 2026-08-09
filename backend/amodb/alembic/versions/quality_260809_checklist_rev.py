"""Add reusable versioned audit checklist templates and immutable audit bindings.

Revision ID: quality_260809_checklist_rev
Revises: quality_260809_audit_notice
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_checklist_rev"
down_revision = "quality_260809_audit_notice"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy} ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        "quality_audit_checklist_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("audit_kind", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_quality_audit_checklist_template_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "template_code", name="uq_quality_audit_checklist_template_code"),
    )
    op.create_index("ix_quality_audit_checklist_template_active", "quality_audit_checklist_templates", ["amo_id", "status", "audit_kind"])

    op.create_table(
        "quality_audit_checklist_template_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("supersedes_revision_id", sa.String(length=36), nullable=True),
        sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_checklist_template_revision_no"),
        sa.CheckConstraint("status IN ('DRAFT','ISSUED')", name="ck_quality_audit_checklist_template_revision_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["quality_audit_checklist_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_revision_id"], ["quality_audit_checklist_template_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "template_id", "revision_no", name="uq_quality_audit_checklist_template_revision"),
    )
    op.create_index("ix_quality_audit_checklist_template_revision", "quality_audit_checklist_template_revisions", ["amo_id", "template_id", "revision_no"])

    op.create_table(
        "quality_audit_checklist_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("template_revision_id", sa.String(length=36), nullable=False),
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("item_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("instantiated_item_ids", sa.JSON(), nullable=False),
        sa.Column("application_reason", sa.Text(), nullable=False),
        sa.Column("applied_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["quality_audit_checklist_templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_revision_id"], ["quality_audit_checklist_template_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "template_revision_id", name="uq_quality_audit_checklist_binding"),
    )
    op.create_index("ix_quality_audit_checklist_binding_audit", "quality_audit_checklist_bindings", ["amo_id", "audit_id", "applied_at"])

    for table_name in (
        "quality_audit_checklist_templates",
        "quality_audit_checklist_template_revisions",
        "quality_audit_checklist_bindings",
    ):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_issued_quality_checklist_revision_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' OR OLD.status = 'ISSUED' THEN
                    RAISE EXCEPTION 'issued audit checklist template revisions are immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_checklist_revision_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_checklist_template_revisions
            FOR EACH ROW EXECUTE FUNCTION prevent_issued_quality_checklist_revision_mutation();
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_checklist_binding_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_checklist_bindings is immutable';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_checklist_binding_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_checklist_bindings
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_checklist_binding_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_checklist_binding_immutable ON quality_audit_checklist_bindings"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_checklist_binding_mutation()"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_checklist_revision_immutable ON quality_audit_checklist_template_revisions"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_issued_quality_checklist_revision_mutation()"))
    for table_name in (
        "quality_audit_checklist_bindings",
        "quality_audit_checklist_template_revisions",
        "quality_audit_checklist_templates",
    ):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_checklist_binding_audit", table_name="quality_audit_checklist_bindings")
    op.drop_table("quality_audit_checklist_bindings")
    op.drop_index("ix_quality_audit_checklist_template_revision", table_name="quality_audit_checklist_template_revisions")
    op.drop_table("quality_audit_checklist_template_revisions")
    op.drop_index("ix_quality_audit_checklist_template_active", table_name="quality_audit_checklist_templates")
    op.drop_table("quality_audit_checklist_templates")
