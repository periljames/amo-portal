"""Add versioned, idempotent live-audit fieldwork mutation receipts.

Revision ID: quality_260816_fieldwork_sync
Revises: quality_260816_report_composition
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_fieldwork_sync"
down_revision = "quality_260816_report_composition"
branch_labels = None
depends_on = None

RECEIPT_TABLE = "quality_audit_fieldwork_mutation_receipts"
CONTRIBUTION_TABLE = "quality_audit_fieldwork_participant_contributions"
GOVERNANCE_TABLE = "quality_audit_checklist_execution_governance"
EVENT_TABLE = "quality_audit_checklist_execution_events"


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
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.add_column(GOVERNANCE_TABLE, sa.Column("entity_version", sa.Integer(), server_default="1", nullable=False))
    op.add_column(GOVERNANCE_TABLE, sa.Column("updated_by_participant_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_quality_checklist_execution_participant", GOVERNANCE_TABLE, "quality_audit_participants",
        ["updated_by_participant_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column(EVENT_TABLE, sa.Column("actor_participant_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_quality_checklist_execution_event_participant", EVENT_TABLE, "quality_audit_participants",
        ["actor_participant_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        RECEIPT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_item_id", sa.Uuid(), nullable=False),
        sa.Column("client_mutation_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("device_sequence", sa.BigInteger(), nullable=False),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("committed_version", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=48), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_participant_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_participant_id"], ["quality_audit_participants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_fieldwork_client_mutation"),
        sa.CheckConstraint("base_version >= 0", name="ck_quality_fieldwork_base_version"),
        sa.CheckConstraint("committed_version >= 1", name="ck_quality_fieldwork_committed_version"),
        sa.CheckConstraint("device_sequence >= 0", name="ck_quality_fieldwork_device_sequence"),
        sa.CheckConstraint("NOT (actor_user_id IS NOT NULL AND actor_participant_id IS NOT NULL)", name="ck_quality_fieldwork_single_actor"),
    )
    op.create_index("ix_quality_fieldwork_receipt_audit_item", RECEIPT_TABLE, ["amo_id", "audit_id", "checklist_item_id", "created_at"])
    op.create_index("ix_quality_fieldwork_receipt_device", RECEIPT_TABLE, ["amo_id", "device_id", "device_sequence"])

    op.create_table(
        CONTRIBUTION_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("checklist_item_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("client_mutation_id", sa.String(length=128), nullable=False),
        sa.Column("canonical_response_status", sa.String(length=24), nullable=False),
        sa.Column("auditor_notes", sa.Text(), nullable=True),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_fieldwork_participant_contribution_mutation"),
        sa.CheckConstraint(
            "canonical_response_status IN ('COMPLIANT','NONCOMPLIANT','OBSERVATION','NOT_APPLICABLE','NOT_VERIFIED')",
            name="ck_quality_fieldwork_participant_response_status",
        ),
    )
    op.create_index(
        "ix_quality_fieldwork_participant_contribution_item",
        CONTRIBUTION_TABLE,
        ["amo_id", "audit_id", "checklist_item_id", "participant_id", "created_at"],
    )

    _enable_rls(RECEIPT_TABLE)
    _enable_rls(CONTRIBUTION_TABLE)
    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_fieldwork_receipts_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_fieldwork_mutation_receipts is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_quality_fieldwork_receipts_append_only
            BEFORE UPDATE OR DELETE ON {RECEIPT_TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_fieldwork_receipts_mutation();
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_fieldwork_contributions_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_fieldwork_participant_contributions is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_quality_fieldwork_contributions_append_only
            BEFORE UPDATE OR DELETE ON {CONTRIBUTION_TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_fieldwork_contributions_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_quality_fieldwork_contributions_append_only ON {CONTRIBUTION_TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_fieldwork_contributions_mutation()"))
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_quality_fieldwork_receipts_append_only ON {RECEIPT_TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_fieldwork_receipts_mutation()"))
    _disable_rls(CONTRIBUTION_TABLE)
    _disable_rls(RECEIPT_TABLE)
    op.drop_index("ix_quality_fieldwork_participant_contribution_item", table_name=CONTRIBUTION_TABLE)
    op.drop_table(CONTRIBUTION_TABLE)
    op.drop_index("ix_quality_fieldwork_receipt_device", table_name=RECEIPT_TABLE)
    op.drop_index("ix_quality_fieldwork_receipt_audit_item", table_name=RECEIPT_TABLE)
    op.drop_table(RECEIPT_TABLE)
    op.drop_constraint("fk_quality_checklist_execution_event_participant", EVENT_TABLE, type_="foreignkey")
    op.drop_column(EVENT_TABLE, "actor_participant_id")
    op.drop_constraint("fk_quality_checklist_execution_participant", GOVERNANCE_TABLE, type_="foreignkey")
    op.drop_column(GOVERNANCE_TABLE, "updated_by_participant_id")
    op.drop_column(GOVERNANCE_TABLE, "entity_version")
