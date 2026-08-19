"""Add governed live-audit evidence artifacts.

Revision ID: quality_260817_evidence_artifacts
Revises: quality_260817_live_audit_completion
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260817_evidence_artifacts"
down_revision = "quality_260817_live_audit_completion"
branch_labels = None
depends_on = None

TABLE = "quality_audit_evidence_artifacts"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_item_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("client_mutation_id", sa.String(length=128), nullable=True),
        sa.Column("file_ref", sa.String(length=1024), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("uploaded_by_participant_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["qms_audit_findings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_participant_id"], ["quality_audit_participants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_audit_evidence_client_mutation"),
        sa.CheckConstraint("source_type IN ('INTERNAL_USER','EXTERNAL_AUDITOR','AUDITEE_GUEST')", name="ck_quality_audit_evidence_source"),
        sa.CheckConstraint(
            "NOT (uploaded_by_user_id IS NOT NULL AND uploaded_by_participant_id IS NOT NULL)",
            name="ck_quality_audit_evidence_single_actor",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_quality_audit_evidence_size"),
    )
    op.create_index("ix_quality_audit_evidence_audit", TABLE, ["amo_id", "audit_id", "created_at"])
    op.create_index("ix_quality_audit_evidence_checklist", TABLE, ["amo_id", "audit_id", "checklist_item_id", "created_at"])
    op.create_index("ix_quality_audit_evidence_finding", TABLE, ["amo_id", "audit_id", "finding_id", "created_at"])
    op.create_index("ix_quality_audit_evidence_sha", TABLE, ["amo_id", "audit_id", "sha256"])

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
            CREATE OR REPLACE FUNCTION prevent_quality_audit_evidence_mutation()
            RETURNS trigger AS $$ BEGIN
                RAISE EXCEPTION '% is immutable audit evidence', TG_TABLE_NAME;
            END; $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_{TABLE}_immutable
            BEFORE UPDATE OR DELETE ON {TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_evidence_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON {TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_evidence_mutation()"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_amo_isolation ON \"{TABLE}\""))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_evidence_sha", table_name=TABLE)
    op.drop_index("ix_quality_audit_evidence_finding", table_name=TABLE)
    op.drop_index("ix_quality_audit_evidence_checklist", table_name=TABLE)
    op.drop_index("ix_quality_audit_evidence_audit", table_name=TABLE)
    op.drop_table(TABLE)
