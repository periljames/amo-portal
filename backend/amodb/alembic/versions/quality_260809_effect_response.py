"""Add governed downstream actions for ineffective effectiveness reviews.

Revision ID: quality_260809_effect_response
Revises: quality_260809_programme_occ
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_effect_response"
down_revision = "quality_260809_programme_occ"
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
        "quality_effectiveness_response_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("effectiveness_plan_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="OPEN", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("target_source_type", sa.String(length=64), nullable=True),
        sa.Column("target_source_id", sa.String(length=160), nullable=True),
        sa.Column("target_route", sa.String(length=500), nullable=True),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("action_type IN ('ADDITIONAL_ACTION','FOLLOW_UP_AUDIT','REOPEN_CAR','MANAGEMENT_ESCALATION','RISK_REASSESSMENT')", name="ck_quality_effectiveness_response_type"),
        sa.CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED')", name="ck_quality_effectiveness_response_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_assurance_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["effectiveness_plan_id"], ["quality_effectiveness_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["qms_audit_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_effectiveness_response_case", "quality_effectiveness_response_actions", ["amo_id", "case_id", "status", "created_at"])
    op.create_index("ix_quality_effectiveness_response_plan", "quality_effectiveness_response_actions", ["amo_id", "effectiveness_plan_id", "status"])
    op.create_index("ix_quality_effectiveness_response_due", "quality_effectiveness_response_actions", ["amo_id", "status", "due_date"])

    op.create_table(
        "quality_effectiveness_response_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("response_action_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('OPENED','COMPLETED','CANCELLED')", name="ck_quality_effectiveness_response_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_assurance_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["response_action_id"], ["quality_effectiveness_response_actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_effectiveness_response_events", "quality_effectiveness_response_events", ["amo_id", "case_id", "created_at"])

    for table_name in ("quality_effectiveness_response_actions", "quality_effectiveness_response_events"):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_effectiveness_response_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_effectiveness_response_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_effectiveness_response_events_append_only
            BEFORE UPDATE OR DELETE ON quality_effectiveness_response_events
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_effectiveness_response_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_effectiveness_response_events_append_only ON quality_effectiveness_response_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_effectiveness_response_events_mutation()"))
    for table_name in ("quality_effectiveness_response_events", "quality_effectiveness_response_actions"):
        _disable_rls(table_name)
    op.drop_index("ix_quality_effectiveness_response_events", table_name="quality_effectiveness_response_events")
    op.drop_table("quality_effectiveness_response_events")
    op.drop_index("ix_quality_effectiveness_response_due", table_name="quality_effectiveness_response_actions")
    op.drop_index("ix_quality_effectiveness_response_plan", table_name="quality_effectiveness_response_actions")
    op.drop_index("ix_quality_effectiveness_response_case", table_name="quality_effectiveness_response_actions")
    op.drop_table("quality_effectiveness_response_actions")
