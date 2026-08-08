"""Add versioned governed audit preparation snapshots.

Revision ID: quality_260808_audit_prep
Revises: quality_260808_intelligence_graph
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260808_audit_prep"
down_revision = "quality_260808_intelligence_graph"
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
        "quality_audit_preparation_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("preparation_scope", sa.Text(), nullable=True),
        sa.Column("audit_snapshot", sa.JSON(), nullable=False),
        sa.Column("checklist_snapshot", sa.JSON(), nullable=False),
        sa.Column("document_request_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("supersedes_revision_id", sa.String(length=36), nullable=True),
        sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_preparation_revision_no"),
        sa.CheckConstraint("status IN ('DRAFT','ISSUED')", name="ck_quality_audit_preparation_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_revision_id"], ["quality_audit_preparation_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "revision_no", name="uq_quality_audit_preparation_revision"),
    )
    op.create_index("ix_quality_audit_preparation_audit", "quality_audit_preparation_revisions", ["amo_id", "audit_id", "revision_no"])
    op.create_index("ix_quality_audit_preparation_status", "quality_audit_preparation_revisions", ["amo_id", "status", "created_at"])

    op.create_table(
        "quality_audit_preparation_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('CREATED','ISSUED')", name="ck_quality_audit_preparation_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["quality_audit_preparation_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_preparation_events", "quality_audit_preparation_events", ["amo_id", "audit_id", "created_at"])

    for table_name in ("quality_audit_preparation_revisions", "quality_audit_preparation_events"):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_issued_audit_preparation_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' OR OLD.status = 'ISSUED' THEN
                    RAISE EXCEPTION 'issued audit preparation revisions are immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_preparation_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_preparation_revisions
            FOR EACH ROW EXECUTE FUNCTION prevent_issued_audit_preparation_mutation();
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_preparation_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_preparation_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_preparation_events_append_only
            BEFORE UPDATE OR DELETE ON quality_audit_preparation_events
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_preparation_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_preparation_events_append_only ON quality_audit_preparation_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_preparation_events_mutation()"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_preparation_immutable ON quality_audit_preparation_revisions"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_issued_audit_preparation_mutation()"))
    _disable_rls("quality_audit_preparation_events")
    _disable_rls("quality_audit_preparation_revisions")
    op.drop_index("ix_quality_audit_preparation_events", table_name="quality_audit_preparation_events")
    op.drop_table("quality_audit_preparation_events")
    op.drop_index("ix_quality_audit_preparation_status", table_name="quality_audit_preparation_revisions")
    op.drop_index("ix_quality_audit_preparation_audit", table_name="quality_audit_preparation_revisions")
    op.drop_table("quality_audit_preparation_revisions")
