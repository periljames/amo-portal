"""Add governed audit programme deferral decisions.

Revision ID: quality_260809_deferrals
Revises: quality_260809_closure_state
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_deferrals"
down_revision = "quality_260809_closure_state"
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
        "quality_audit_deferrals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("programme_id", sa.String(length=36), nullable=False),
        sa.Column("programme_item_id", sa.String(length=36), nullable=False),
        sa.Column("original_target_start", sa.Date(), nullable=True),
        sa.Column("original_target_end", sa.Date(), nullable=True),
        sa.Column("revised_target_start", sa.Date(), nullable=False),
        sa.Column("revised_target_end", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk_rating", sa.String(length=16), nullable=False),
        sa.Column("risk_assessment", sa.Text(), nullable=False),
        sa.Column("mitigations", sa.JSON(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("repeated_deferral_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="REQUESTED", nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("applied_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','APPLIED','WITHDRAWN')", name="ck_quality_audit_deferral_status"),
        sa.CheckConstraint("risk_rating IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_audit_deferral_risk"),
        sa.CheckConstraint("repeated_deferral_count >= 0", name="ck_quality_audit_deferral_repeat_count"),
        sa.CheckConstraint("revised_target_end IS NULL OR revised_target_end >= revised_target_start", name="ck_quality_audit_deferral_revised_dates"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["quality_audit_programmes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_item_id"], ["quality_audit_programme_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_deferral_item", "quality_audit_deferrals", ["amo_id", "programme_item_id", "status", "requested_at"])
    op.create_index("ix_quality_audit_deferral_risk", "quality_audit_deferrals", ["amo_id", "risk_rating", "status"])

    op.create_table(
        "quality_audit_deferral_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("programme_item_id", sa.String(length=36), nullable=False),
        sa.Column("deferral_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('REQUESTED','APPROVED','REJECTED','APPLIED','WITHDRAWN')", name="ck_quality_audit_deferral_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_item_id"], ["quality_audit_programme_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deferral_id"], ["quality_audit_deferrals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_deferral_events", "quality_audit_deferral_events", ["amo_id", "programme_item_id", "created_at"])

    for table_name in ("quality_audit_deferrals", "quality_audit_deferral_events"):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_deferral_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_deferral_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_deferral_events_append_only
            BEFORE UPDATE OR DELETE ON quality_audit_deferral_events
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_deferral_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_deferral_events_append_only ON quality_audit_deferral_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_deferral_events_mutation()"))
    for table_name in ("quality_audit_deferral_events", "quality_audit_deferrals"):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_deferral_events", table_name="quality_audit_deferral_events")
    op.drop_table("quality_audit_deferral_events")
    op.drop_index("ix_quality_audit_deferral_risk", table_name="quality_audit_deferrals")
    op.drop_index("ix_quality_audit_deferral_item", table_name="quality_audit_deferrals")
    op.drop_table("quality_audit_deferrals")
