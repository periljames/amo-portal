"""Add generated closing-report artifacts.

Revision ID: quality_260816_report_composition
Revises: quality_260816_guest_documents
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_report_composition"
down_revision = "quality_260816_guest_documents"
branch_labels = None
depends_on = None

TABLE = "quality_audit_report_artifacts"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("renderer_version", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_quality_audit_report_artifact_size"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_audit_report_artifact_audit",
        TABLE,
        ["amo_id", "audit_id", "created_at"],
    )
    op.create_index(
        "ix_quality_audit_report_artifact_snapshot",
        TABLE,
        ["amo_id", "audit_id", "source_snapshot_hash"],
    )
    op.create_index(
        "ix_quality_audit_report_artifact_hash",
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
            CREATE OR REPLACE FUNCTION prevent_quality_audit_report_artifact_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Generated audit report artifact history is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_{TABLE}_append_only
            BEFORE UPDATE OR DELETE ON {TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_report_artifact_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_append_only ON {TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_report_artifact_mutation()"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_amo_isolation ON \"{TABLE}\""))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_report_artifact_hash", table_name=TABLE)
    op.drop_index("ix_quality_audit_report_artifact_snapshot", table_name=TABLE)
    op.drop_index("ix_quality_audit_report_artifact_audit", table_name=TABLE)
    op.drop_table(TABLE)
