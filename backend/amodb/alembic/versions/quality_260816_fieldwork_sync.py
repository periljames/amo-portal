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
GOVERNANCE_TABLE = "quality_audit_checklist_execution_governance"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        GOVERNANCE_TABLE,
        sa.Column("entity_version", sa.Integer(), server_default="1", nullable=False),
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["quality_audit_checklist_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "client_mutation_id", name="uq_quality_fieldwork_client_mutation"),
        sa.CheckConstraint("base_version >= 0", name="ck_quality_fieldwork_base_version"),
        sa.CheckConstraint("committed_version >= 1", name="ck_quality_fieldwork_committed_version"),
        sa.CheckConstraint("device_sequence >= 0", name="ck_quality_fieldwork_device_sequence"),
    )
    op.create_index(
        "ix_quality_fieldwork_receipt_audit_item",
        RECEIPT_TABLE,
        ["amo_id", "audit_id", "checklist_item_id", "created_at"],
    )
    op.create_index(
        "ix_quality_fieldwork_receipt_device",
        RECEIPT_TABLE,
        ["amo_id", "device_id", "device_sequence"],
    )

    if _is_postgresql():
        policy = f"{RECEIPT_TABLE}_amo_isolation"
        op.execute(sa.text(f'ALTER TABLE "{RECEIPT_TABLE}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{RECEIPT_TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"""
            CREATE POLICY {policy}
            ON "{RECEIPT_TABLE}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))
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


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_quality_fieldwork_receipts_append_only ON {RECEIPT_TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_fieldwork_receipts_mutation()"))
        op.execute(sa.text(f'DROP POLICY IF EXISTS {RECEIPT_TABLE}_amo_isolation ON "{RECEIPT_TABLE}"'))
        op.execute(sa.text(f'ALTER TABLE "{RECEIPT_TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{RECEIPT_TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_fieldwork_receipt_device", table_name=RECEIPT_TABLE)
    op.drop_index("ix_quality_fieldwork_receipt_audit_item", table_name=RECEIPT_TABLE)
    op.drop_table(RECEIPT_TABLE)
    op.drop_column(GOVERNANCE_TABLE, "entity_version")
