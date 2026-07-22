"""QMS audit schedule tenant control and frontend-edit support.

Revision ID: phase2_12_20260607
Revises: phase2_11_20260605
Create Date: 2026-06-07

This migration is commutative with the audit-scope branch. If scope definitions
land first, schedule scope references are normalised after ``amo_id`` is added.
If they land later, the scope repair migration performs the same update.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "phase2_12_20260607"
down_revision = "phase2_11_20260605"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                LIMIT 1
                """
            ),
            {"table_name": table_name},
        ).first()
    )


def _columns(bind, table_name: str) -> set[str]:
    if not _table_exists(bind, table_name):
        return set()
    rows = bind.execute(
        sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalars()
    return {str(row) for row in rows}


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    return column_name in _columns(bind, table_name)


def _has_columns(bind, table_name: str, columns: set[str]) -> bool:
    return columns.issubset(_columns(bind, table_name))


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = current_schema()
                  AND t.relname = :table_name
                  AND c.conname = :constraint_name
                LIMIT 1
                """
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).first()
    )


def _backfill_from_user_link(bind, schedule_column: str) -> None:
    if not _has_columns(bind, "qms_audit_schedules", {"amo_id", schedule_column}):
        return
    if not _has_columns(bind, "users", {"id", "amo_id"}):
        return
    bind.execute(
        sa.text(
            f"""
            UPDATE qms_audit_schedules s
            SET amo_id = u.amo_id
            FROM users u
            WHERE s.amo_id IS NULL
              AND s.{schedule_column} IS NOT NULL
              AND u.id = s.{schedule_column}
              AND u.amo_id IS NOT NULL
            """
        )
    )


def _backfill_single_tenant(bind) -> None:
    if not _has_columns(bind, "qms_audit_schedules", {"amo_id"}):
        return
    amo_columns = _columns(bind, "amos")
    if "id" not in amo_columns:
        return
    order_sql = "created_at NULLS LAST, id" if "created_at" in amo_columns else "id"
    bind.execute(
        sa.text(
            f"""
            WITH single_amo AS (
                SELECT id FROM amos ORDER BY {order_sql} LIMIT 1
            )
            UPDATE qms_audit_schedules s
            SET amo_id = single_amo.id
            FROM single_amo
            WHERE s.amo_id IS NULL
              AND (SELECT COUNT(*) FROM amos) = 1
            """
        )
    )


def _normalise_scope_references(bind) -> None:
    schedule_required = {"amo_id", "kind", "audit_scope_id", "audit_scope_code"}
    scope_required = {"id", "amo_id", "code"}
    if not _has_columns(bind, "qms_audit_schedules", schedule_required):
        return
    if not _has_columns(bind, "qms_audit_scopes", scope_required):
        return

    bind.execute(
        sa.text(
            """
            UPDATE qms_audit_schedules s
            SET audit_scope_code = COALESCE(NULLIF(s.audit_scope_code, ''), ds.code, 'MO'),
                audit_scope_id = COALESCE(s.audit_scope_id, ds.id)
            FROM qms_audit_scopes ds
            WHERE ds.amo_id = s.amo_id
              AND ds.code = CASE
                    WHEN s.kind = 'THIRD_PARTY' THEN 'REG'
                    WHEN s.kind = 'EXTERNAL' THEN 'SC'
                    ELSE 'MO'
                  END
              AND (s.audit_scope_code IS NULL OR s.audit_scope_code = '' OR s.audit_scope_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE qms_audit_schedules
            SET audit_scope_code = COALESCE(
                NULLIF(audit_scope_code, ''),
                CASE WHEN kind = 'THIRD_PARTY' THEN 'REG' WHEN kind = 'EXTERNAL' THEN 'SC' ELSE 'MO' END
            )
            WHERE audit_scope_code IS NULL OR audit_scope_code = ''
            """
        )
    )


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

    for schedule_column in ("created_by_user_id", "lead_auditor_user_id", "auditee_user_id"):
        _backfill_from_user_link(bind, schedule_column)
    _backfill_single_tenant(bind)

    if (
        _has_columns(bind, "qms_audit_schedules", {"amo_id"})
        and _has_columns(bind, "amos", {"id"})
        and not _constraint_exists(bind, "qms_audit_schedules", "fk_qms_audit_schedules_amo_id")
    ):
        op.create_foreign_key(
            "fk_qms_audit_schedules_amo_id",
            "qms_audit_schedules",
            "amos",
            ["amo_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if _has_columns(bind, "qms_audit_schedules", {"amo_id", "next_due_date", "id"}):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_amo_due_id "
            "ON qms_audit_schedules (amo_id, next_due_date, id) WHERE next_due_date IS NOT NULL"
        )
    if _has_columns(bind, "qms_audit_schedules", {"amo_id", "is_active", "id"}):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_amo_active_id "
            "ON qms_audit_schedules (amo_id, is_active, id)"
        )

    _normalise_scope_references(bind)
    op.execute("ANALYZE qms_audit_schedules")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _table_exists(bind, "qms_audit_schedules"):
        return
    op.execute("DROP INDEX IF EXISTS ix_qms_audit_schedules_amo_due_id")
    op.execute("DROP INDEX IF EXISTS ix_qms_audit_schedules_amo_active_id")
    if _constraint_exists(bind, "qms_audit_schedules", "fk_qms_audit_schedules_amo_id"):
        op.drop_constraint("fk_qms_audit_schedules_amo_id", "qms_audit_schedules", type_="foreignkey")
    # Keep amo_id on downgrade to avoid tenant-association data loss.
