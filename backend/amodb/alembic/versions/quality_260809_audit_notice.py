"""Add governed audit notice policies, revisions and immutable events.

Revision ID: quality_260809_audit_notice
Revises: quality_260808_audit_prep
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_audit_notice"
down_revision = "quality_260808_audit_prep"
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
        "quality_audit_notice_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("policy_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audit_kind", sa.String(length=32), nullable=True),
        sa.Column("minimum_notice_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("review_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("acknowledgement_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("emergency_exception_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("unannounced_exception_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("minimum_notice_days >= 0", name="ck_quality_audit_notice_policy_days"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "policy_code", name="uq_quality_audit_notice_policy_code"),
    )
    op.create_index("ix_quality_audit_notice_policy_active", "quality_audit_notice_policies", ["amo_id", "is_active", "audit_kind"])

    op.create_table(
        "quality_audit_notices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=True),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("required_notice_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("notice_date", sa.Date(), nullable=False),
        sa.Column("exception_type", sa.String(length=16), nullable=True),
        sa.Column("exception_reason", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audit_snapshot", sa.JSON(), nullable=False),
        sa.Column("recipient_snapshot", sa.JSON(), nullable=False),
        sa.Column("delivery_channel", sa.String(length=32), nullable=True),
        sa.Column("delivery_reference", sa.String(length=512), nullable=True),
        sa.Column("supersedes_notice_id", sa.String(length=36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_notice_revision_no"),
        sa.CheckConstraint("required_notice_days >= 0", name="ck_quality_audit_notice_required_days"),
        sa.CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','GENERATED','DELIVERED','ACKNOWLEDGED','SUPERSEDED','CANCELLED')", name="ck_quality_audit_notice_status"),
        sa.CheckConstraint("exception_type IS NULL OR exception_type IN ('EMERGENCY','UNANNOUNCED')", name="ck_quality_audit_notice_exception_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["quality_audit_notice_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_notice_id"], ["quality_audit_notices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["delivered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "revision_no", name="uq_quality_audit_notice_revision"),
    )
    op.create_index("ix_quality_audit_notice_audit", "quality_audit_notices", ["amo_id", "audit_id", "revision_no"])
    op.create_index("ix_quality_audit_notice_status", "quality_audit_notices", ["amo_id", "status", "notice_date"])

    op.create_table(
        "quality_audit_notice_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("notice_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('CREATED','SUBMITTED','RETURNED','APPROVED','GENERATED','DELIVERED','ACKNOWLEDGED','REVISED','CANCELLED')", name="ck_quality_audit_notice_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_id"], ["quality_audit_notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_notice_events", "quality_audit_notice_events", ["amo_id", "audit_id", "created_at"])

    for table_name in ("quality_audit_notice_policies", "quality_audit_notices", "quality_audit_notice_events"):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_terminal_quality_audit_notice_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'audit notice revisions cannot be deleted';
                END IF;
                IF OLD.status IN ('ACKNOWLEDGED','SUPERSEDED','CANCELLED') THEN
                    RAISE EXCEPTION 'terminal audit notice revisions are immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_notice_terminal_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_notices
            FOR EACH ROW EXECUTE FUNCTION prevent_terminal_quality_audit_notice_mutation();
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_notice_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_notice_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_notice_events_append_only
            BEFORE UPDATE OR DELETE ON quality_audit_notice_events
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_notice_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_notice_events_append_only ON quality_audit_notice_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_notice_events_mutation()"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_notice_terminal_immutable ON quality_audit_notices"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_terminal_quality_audit_notice_mutation()"))
    for table_name in ("quality_audit_notice_events", "quality_audit_notices", "quality_audit_notice_policies"):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_notice_events", table_name="quality_audit_notice_events")
    op.drop_table("quality_audit_notice_events")
    op.drop_index("ix_quality_audit_notice_status", table_name="quality_audit_notices")
    op.drop_index("ix_quality_audit_notice_audit", table_name="quality_audit_notices")
    op.drop_table("quality_audit_notices")
    op.drop_index("ix_quality_audit_notice_policy_active", table_name="quality_audit_notice_policies")
    op.drop_table("quality_audit_notice_policies")
