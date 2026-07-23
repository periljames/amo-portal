"""QMS dashboard/calendar read stability indexes.

Revision ID: qms_20260607_read_stability
Revises: None
Create Date: 2026-06-07

This historical branch may run before tenant-normalisation branches. Indexes are
therefore created only when every referenced column exists; a terminal SaaS
finalizer reapplies the complete set after schema convergence.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "qms_20260607_read_stability"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _create_if_columns(
    bind,
    table_name: str,
    required_columns: Iterable[str],
    sql: str,
) -> None:
    if set(required_columns).issubset(_columns(bind, table_name)):
        op.execute(sa.text(sql))


def upgrade() -> None:
    bind = op.get_bind()
    index_specs = (
        (
            "qms_audits",
            ("amo_id", "status", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_id ON qms_audits (amo_id, status, id)",
        ),
        (
            "qms_audits",
            ("amo_id", "planned_start", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_id ON qms_audits (amo_id, planned_start, id) WHERE planned_start IS NOT NULL",
        ),
        (
            "qms_audits",
            ("amo_id", "planned_end", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_id ON qms_audits (amo_id, planned_end, id) WHERE planned_end IS NOT NULL",
        ),
        (
            "qms_audits",
            ("amo_id", "created_at", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_id ON qms_audits (amo_id, created_at DESC, id)",
        ),
        (
            "quality_cars",
            ("amo_id", "status", "id"),
            "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_status_id ON quality_cars (amo_id, status, id)",
        ),
        (
            "quality_cars",
            ("amo_id", "due_date", "id"),
            "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_id ON quality_cars (amo_id, due_date, id) WHERE due_date IS NOT NULL",
        ),
        (
            "qms_audit_findings",
            ("amo_id", "closed_at", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_findings_amo_closed_id ON qms_audit_findings (amo_id, closed_at, id)",
        ),
        (
            "qms_documents",
            ("amo_id", "status", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_documents_amo_status_id ON qms_documents (amo_id, status, id)",
        ),
        (
            "training_records",
            ("amo_id", "user_id", "course_id", "completion_date", "created_at", "id"),
            "CREATE INDEX IF NOT EXISTS ix_training_records_amo_user_course_latest ON training_records (amo_id, user_id, course_id, completion_date DESC, created_at DESC, id DESC)",
        ),
        (
            "training_records",
            ("amo_id", "valid_until", "id"),
            "CREATE INDEX IF NOT EXISTS ix_training_records_amo_valid_until_id ON training_records (amo_id, valid_until, id) WHERE valid_until IS NOT NULL",
        ),
    )
    for table_name, required_columns, sql in index_specs:
        _create_if_columns(bind, table_name, required_columns, sql)

    for table_name in (
        "qms_audits",
        "quality_cars",
        "qms_audit_findings",
        "qms_documents",
        "training_records",
    ):
        if _table_exists(bind, table_name):
            op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for index_name in (
        "ix_qms_audits_amo_status_id",
        "ix_qms_audits_amo_planned_start_id",
        "ix_qms_audits_amo_planned_end_id",
        "ix_qms_audits_amo_created_id",
        "ix_quality_cars_amo_status_id",
        "ix_quality_cars_amo_due_id",
        "ix_qms_findings_amo_closed_id",
        "ix_qms_documents_amo_status_id",
        "ix_training_records_amo_user_course_latest",
        "ix_training_records_amo_valid_until_id",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
