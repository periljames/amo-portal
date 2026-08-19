"""Add immutable external-auditor finding drafts and append-only lifecycle events.

Revision ID: quality_260816_external_finding_drafts
Revises: quality_260816_fieldwork_sync
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_external_finding_drafts"
down_revision = "quality_260816_fieldwork_sync"
branch_labels = None
depends_on = None

DRAFT_TABLE = "quality_audit_external_finding_drafts"
EVENT_TABLE = "quality_audit_external_finding_draft_events"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy}
        ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    op.execute(sa.text(f'DROP POLICY IF EXISTS {table_name}_amo_isolation ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        DRAFT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_item_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("client_mutation_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("device_sequence", sa.BigInteger(), nullable=False),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("draft_type", sa.String(length=24), nullable=False),
        sa.Column("proposed_severity", sa.String(length=16), nullable=False),
        sa.Column("proposed_level", sa.String(length=16), nullable=False),
        sa.Column("requirement_ref", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("objective_evidence", sa.Text(), nullable=True),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("supersedes_draft_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_draft_id"], [f"{DRAFT_TABLE}.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_external_finding_draft_mutation"),
        sa.CheckConstraint("draft_type IN ('NON_CONFORMITY','OBSERVATION')", name="ck_quality_external_finding_draft_type"),
        sa.CheckConstraint("proposed_severity IN ('MINOR','MAJOR','CRITICAL')", name="ck_quality_external_finding_draft_severity"),
        sa.CheckConstraint("proposed_level IN ('LEVEL_1','LEVEL_2','LEVEL_3','LEVEL_4')", name="ck_quality_external_finding_draft_level"),
        sa.CheckConstraint("device_sequence >= 0", name="ck_quality_external_finding_draft_device_sequence"),
    )
    op.create_index(
        "ix_quality_external_finding_draft_audit",
        DRAFT_TABLE,
        ["amo_id", "audit_id", "checklist_item_id", "participant_id", "created_at"],
    )

    op.create_table(
        EVENT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_participant_id", sa.String(length=36), nullable=True),
        sa.Column("promoted_finding_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["draft_id"], [f"{DRAFT_TABLE}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_participant_id"], ["quality_audit_participants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["promoted_finding_id"], ["qms_audit_findings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("event_type IN ('CREATED','SUBMITTED','RETURNED','PROMOTED','WITHDRAWN')", name="ck_quality_external_finding_draft_event_type"),
        sa.CheckConstraint("NOT (actor_user_id IS NOT NULL AND actor_participant_id IS NOT NULL)", name="ck_quality_external_finding_draft_single_actor"),
    )
    op.create_index(
        "ix_quality_external_finding_draft_events",
        EVENT_TABLE,
        ["amo_id", "audit_id", "draft_id", "created_at"],
    )

    _enable_rls(DRAFT_TABLE)
    _enable_rls(EVENT_TABLE)
    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_external_finding_drafts_mutation()
            RETURNS trigger AS $$ BEGIN
                RAISE EXCEPTION 'quality_audit_external_finding_drafts is immutable; create a superseding draft revision instead';
            END; $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_quality_external_finding_drafts_append_only
            BEFORE UPDATE OR DELETE ON {DRAFT_TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_external_finding_drafts_mutation();
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_external_finding_draft_events_mutation()
            RETURNS trigger AS $$ BEGIN
                RAISE EXCEPTION 'quality_audit_external_finding_draft_events is append-only';
            END; $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_quality_external_finding_draft_events_append_only
            BEFORE UPDATE OR DELETE ON {EVENT_TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_external_finding_draft_events_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_quality_external_finding_draft_events_append_only ON {EVENT_TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_external_finding_draft_events_mutation()"))
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_quality_external_finding_drafts_append_only ON {DRAFT_TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_external_finding_drafts_mutation()"))
    _disable_rls(EVENT_TABLE)
    _disable_rls(DRAFT_TABLE)
    op.drop_index("ix_quality_external_finding_draft_events", table_name=EVENT_TABLE)
    op.drop_table(EVENT_TABLE)
    op.drop_index("ix_quality_external_finding_draft_audit", table_name=DRAFT_TABLE)
    op.drop_table(DRAFT_TABLE)
