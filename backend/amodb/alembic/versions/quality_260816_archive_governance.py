"""Add policy-driven audit archive, legal hold and disposition governance.

Revision ID: quality_260816_archive_governance
Revises: quality_260816_closing_assurance
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_archive_governance"
down_revision = "quality_260816_closing_assurance"
branch_labels = None
depends_on = None

POLICY_TABLE = "quality_audit_retention_policy_revisions"
MANIFEST_TABLE = "quality_audit_archive_manifests"
ITEM_TABLE = "quality_audit_archive_manifest_items"
HOLD_TABLE = "quality_audit_legal_hold_events"
DISPOSITION_TABLE = "quality_audit_disposition_events"
TABLES = (POLICY_TABLE, MANIFEST_TABLE, ITEM_TABLE, HOLD_TABLE, DISPOSITION_TABLE)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {table_name}_amo_isolation
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
        POLICY_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("retention_class", sa.String(length=96), nullable=False),
        sa.Column("record_type", sa.String(length=32), nullable=False),
        sa.Column("retention_start_event", sa.String(length=32), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("indefinite", sa.Boolean(), nullable=False),
        sa.Column("governing_basis", sa.Text(), nullable=False),
        sa.Column("review_before_disposition", sa.Boolean(), nullable=False),
        sa.Column("legal_hold_supported", sa.Boolean(), nullable=False),
        sa.Column("disposition_mode", sa.String(length=48), nullable=False),
        sa.Column("approving_capability", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "revision_no", name="uq_quality_audit_retention_policy_revision"),
        sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_retention_policy_revision_no"),
        sa.CheckConstraint("record_type = 'AUDIT_PACKAGE'", name="ck_quality_audit_retention_record_type"),
        sa.CheckConstraint("retention_start_event IN ('EXECUTION_CLOSED','FOLLOW_UP_COMPLETE')", name="ck_quality_audit_retention_start_event"),
        sa.CheckConstraint("disposition_mode IN ('PRESERVE_METADATA_DELETE_PACKAGE','TRANSFER_PACKAGE','NO_DISPOSITION')", name="ck_quality_audit_retention_disposition_mode"),
        sa.CheckConstraint("(indefinite IS TRUE AND duration_days IS NULL) OR (indefinite IS FALSE AND duration_days IS NOT NULL AND duration_days > 0)", name="ck_quality_audit_retention_duration_rule"),
    )
    op.create_index("ix_quality_audit_retention_policy_latest", POLICY_TABLE, ["amo_id", "revision_no"])

    op.create_table(
        MANIFEST_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("retention_policy_revision_id", sa.String(length=36), nullable=False),
        sa.Column("retention_class", sa.String(length=96), nullable=False),
        sa.Column("retention_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retention_policy_revision_id"], [f"{POLICY_TABLE}.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "manifest_version", name="uq_quality_audit_archive_manifest_version"),
        sa.CheckConstraint("manifest_version >= 1", name="ck_quality_audit_archive_manifest_version"),
        sa.CheckConstraint("item_count >= 0", name="ck_quality_audit_archive_manifest_item_count"),
    )
    op.create_index("ix_quality_audit_archive_manifest_latest", MANIFEST_TABLE, ["amo_id", "audit_id", "manifest_version"])
    op.create_index("ix_quality_audit_archive_manifest_due", MANIFEST_TABLE, ["amo_id", "retention_due_at"])

    op.create_table(
        ITEM_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("authoritative_record_id", sa.String(length=255), nullable=False),
        sa.Column("revision_ref", sa.String(length=255), nullable=True),
        sa.Column("source_system", sa.String(length=96), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("retention_role", sa.String(length=96), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manifest_id"], [f"{MANIFEST_TABLE}.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_archive_item_manifest", ITEM_TABLE, ["amo_id", "audit_id", "manifest_id", "item_type"])

    op.create_table(
        HOLD_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_id", sa.String(length=36), nullable=True),
        sa.Column("hold_key", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("governing_basis", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manifest_id"], [f"{MANIFEST_TABLE}.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("event_type IN ('PLACED','RELEASED')", name="ck_quality_audit_legal_hold_event_type"),
    )
    op.create_index("ix_quality_audit_legal_hold_latest", HOLD_TABLE, ["amo_id", "audit_id", "hold_key", "created_at"])

    op.create_table(
        DISPOSITION_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("manifest_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("disposition_mode", sa.String(length=48), nullable=False),
        sa.Column("inventory_sha256", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manifest_id"], [f"{MANIFEST_TABLE}.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("event_type IN ('APPROVED','REJECTED','EXECUTED')", name="ck_quality_audit_disposition_event_type"),
    )
    op.create_index("ix_quality_audit_disposition_events", DISPOSITION_TABLE, ["amo_id", "audit_id", "manifest_id", "created_at"])

    for table_name in TABLES:
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_archive_governance_mutation()
            RETURNS trigger AS $$ BEGIN
                RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;
            END; $$ LANGUAGE plpgsql;
        """))
        for table_name in TABLES:
            op.execute(sa.text(f"""
                CREATE TRIGGER trg_{table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION prevent_quality_archive_governance_mutation();
            """))


def downgrade() -> None:
    if _is_postgresql():
        for table_name in reversed(TABLES):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_archive_governance_mutation()"))
    for table_name in reversed(TABLES):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_disposition_events", table_name=DISPOSITION_TABLE)
    op.drop_table(DISPOSITION_TABLE)
    op.drop_index("ix_quality_audit_legal_hold_latest", table_name=HOLD_TABLE)
    op.drop_table(HOLD_TABLE)
    op.drop_index("ix_quality_audit_archive_item_manifest", table_name=ITEM_TABLE)
    op.drop_table(ITEM_TABLE)
    op.drop_index("ix_quality_audit_archive_manifest_due", table_name=MANIFEST_TABLE)
    op.drop_index("ix_quality_audit_archive_manifest_latest", table_name=MANIFEST_TABLE)
    op.drop_table(MANIFEST_TABLE)
    op.drop_index("ix_quality_audit_retention_policy_latest", table_name=POLICY_TABLE)
    op.drop_table(POLICY_TABLE)
