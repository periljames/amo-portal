"""Separate audit execution closure from assurance follow-up completion.

Revision ID: quality_260809_closure_state
Revises: quality_260809_report_rev
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_closure_state"
down_revision = "quality_260809_report_rev"
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
        "quality_audit_closure_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("execution_status", sa.String(length=16), server_default="OPEN", nullable=False),
        sa.Column("execution_closed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("execution_closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_close_reason", sa.Text(), nullable=True),
        sa.Column("execution_evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("follow_up_status", sa.String(length=16), server_default="OPEN", nullable=False),
        sa.Column("follow_up_completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("follow_up_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_completion_reason", sa.Text(), nullable=True),
        sa.Column("follow_up_evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("execution_status IN ('OPEN','CLOSED')", name="ck_quality_audit_execution_status"),
        sa.CheckConstraint("follow_up_status IN ('OPEN','COMPLETE')", name="ck_quality_audit_follow_up_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_closed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["follow_up_completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", name="uq_quality_audit_closure_state"),
    )
    op.create_index("ix_quality_audit_closure_state", "quality_audit_closure_states", ["amo_id", "execution_status", "follow_up_status"])

    op.create_table(
        "quality_audit_closure_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("closure_state_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('EXECUTION_CLOSED','FOLLOW_UP_COMPLETED','FOLLOW_UP_REOPENED')", name="ck_quality_audit_closure_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["closure_state_id"], ["quality_audit_closure_states.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_closure_events", "quality_audit_closure_events", ["amo_id", "audit_id", "created_at"])

    for table_name in ("quality_audit_closure_states", "quality_audit_closure_events"):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_closure_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_closure_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_closure_events_append_only
            BEFORE UPDATE OR DELETE ON quality_audit_closure_events
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_closure_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_closure_events_append_only ON quality_audit_closure_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_closure_events_mutation()"))
    for table_name in ("quality_audit_closure_events", "quality_audit_closure_states"):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_closure_events", table_name="quality_audit_closure_events")
    op.drop_table("quality_audit_closure_events")
    op.drop_index("ix_quality_audit_closure_state", table_name="quality_audit_closure_states")
    op.drop_table("quality_audit_closure_states")
