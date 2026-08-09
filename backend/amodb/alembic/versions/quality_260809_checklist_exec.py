"""Add canonical checklist execution governance.

Revision ID: quality_260809_checklist_exec
Revises: quality_260809_effect_response
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_checklist_exec"
down_revision = "quality_260809_effect_response"
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
        "quality_audit_checklist_execution_governance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_item_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_response_status", sa.String(length=24), server_default="NOT_VERIFIED", nullable=False),
        sa.Column("auditor_notes", sa.Text(), nullable=True),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "canonical_response_status IN ('COMPLIANT','NONCOMPLIANT','OBSERVATION','NOT_APPLICABLE','NOT_VERIFIED')",
            name="ck_quality_checklist_execution_canonical_status",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "checklist_item_id", name="uq_quality_checklist_execution_item"),
    )
    op.create_index(
        "ix_quality_checklist_execution_audit",
        "quality_audit_checklist_execution_governance",
        ["amo_id", "audit_id", "canonical_response_status"],
    )

    op.create_table(
        "quality_audit_checklist_execution_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_item_id", sa.Uuid(), nullable=False),
        sa.Column("governance_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('CREATED','UPDATED')", name="ck_quality_checklist_execution_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["governance_id"], ["quality_audit_checklist_execution_governance.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_checklist_execution_events",
        "quality_audit_checklist_execution_events",
        ["amo_id", "audit_id", "created_at"],
    )

    for table_name in ("quality_audit_checklist_execution_governance", "quality_audit_checklist_execution_events"):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_checklist_execution_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_checklist_execution_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_checklist_execution_events_append_only
            BEFORE UPDATE OR DELETE ON quality_audit_checklist_execution_events
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_checklist_execution_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_checklist_execution_events_append_only ON quality_audit_checklist_execution_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_checklist_execution_events_mutation()"))
    for table_name in ("quality_audit_checklist_execution_events", "quality_audit_checklist_execution_governance"):
        _disable_rls(table_name)
    op.drop_index("ix_quality_checklist_execution_events", table_name="quality_audit_checklist_execution_events")
    op.drop_table("quality_audit_checklist_execution_events")
    op.drop_index("ix_quality_checklist_execution_audit", table_name="quality_audit_checklist_execution_governance")
    op.drop_table("quality_audit_checklist_execution_governance")
