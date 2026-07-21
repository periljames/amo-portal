"""QMS audit schedule tenant control and frontend-edit support.

Revision ID: phase2_12_20260607
Revises: phase2_11_20260605
Create Date: 2026-06-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "phase2_12_20260607"
down_revision = "phase2_11_20260605"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return bool(bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = :table_name
        LIMIT 1
    """), {"table_name": table_name}).first())


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return bool(bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
          AND column_name = :column_name
        LIMIT 1
    """), {"table_name": table_name, "column_name": column_name}).first())


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    return bool(bind.execute(sa.text("""
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND t.relname = :table_name
          AND c.conname = :constraint_name
        LIMIT 1
    """), {"table_name": table_name, "constraint_name": constraint_name}).first())


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _table_exists(bind, "qms_audit_schedules"):
        return

    if not _column_exists(bind, "qms_audit_schedules", "amo_id"):
        op.add_column("qms_audit_schedules", sa.Column("amo_id", sa.String(length=36), nullable=True))

    for column_name, ddl in (
        ("external_auditees_json", "TEXT"),
        ("notify_auditors", "BOOLEAN DEFAULT TRUE"),
        ("notify_auditees", "BOOLEAN DEFAULT TRUE"),
        ("reminder_interval_days", "INTEGER DEFAULT 7"),
    ):
        if not _column_exists(bind, "qms_audit_schedules", column_name):
            op.execute(sa.text(f"ALTER TABLE qms_audit_schedules ADD COLUMN {column_name} {ddl}"))

    bind.execute(sa.text("""
        UPDATE qms_audit_schedules s
        SET amo_id = u.amo_id
        FROM users u
        WHERE s.amo_id IS NULL
          AND s.created_by_user_id IS NOT NULL
          AND u.id = s.created_by_user_id
          AND u.amo_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE qms_audit_schedules s
        SET amo_id = u.amo_id
        FROM users u
        WHERE s.amo_id IS NULL
          AND s.lead_auditor_user_id IS NOT NULL
          AND u.id = s.lead_auditor_user_id
          AND u.amo_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE qms_audit_schedules s
        SET amo_id = u.amo_id
        FROM users u
        WHERE s.amo_id IS NULL
          AND s.auditee_user_id IS NOT NULL
          AND u.id = s.auditee_user_id
          AND u.amo_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        WITH single_amo AS (
            SELECT id FROM amos ORDER BY created_at NULLS LAST, id LIMIT 1
        )
        UPDATE qms_audit_schedules s
        SET amo_id = single_amo.id
        FROM single_amo
        WHERE s.amo_id IS NULL
          AND (SELECT COUNT(*) FROM amos) = 1
    """))

    if not _constraint_exists(bind, "qms_audit_schedules", "fk_qms_audit_schedules_amo_id"):
        op.create_foreign_key(
            "fk_qms_audit_schedules_amo_id",
            "qms_audit_schedules",
            "amos",
            ["amo_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_amo_due_id ON qms_audit_schedules (amo_id, next_due_date, id) WHERE next_due_date IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_amo_active_id ON qms_audit_schedules (amo_id, is_active, id)")
    op.execute("ANALYZE qms_audit_schedules")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _table_exists(bind, "qms_audit_schedules"):
        return
    op.execute("DROP INDEX IF EXISTS ix_qms_audit_schedules_amo_due_id")
    op.execute("DROP INDEX IF EXISTS ix_qms_audit_schedules_amo_active_id")
    if _constraint_exists(bind, "qms_audit_schedules", "fk_qms_audit_schedules_amo_id"):
        op.drop_constraint("fk_qms_audit_schedules_amo_id", "qms_audit_schedules", type_="foreignkey")
    # Keep the column on downgrade to avoid data loss in tenant-scoped deployments.
