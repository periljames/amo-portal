"""QMS audit dashboard and calendar read stability indexes.

Revision ID: phase2_10_20260605
Revises: phase2_9_20260605
Create Date: 2026-06-05

The migration can precede tenant-normalisation branches, so every index is
guarded by its complete referenced-column contract.
"""

from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_10_20260605"
down_revision = "phase2_9_20260605"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _exec_if_columns(table_name: str, columns: Iterable[str], sql: str) -> None:
    if set(columns).issubset(_columns(table_name)):
        op.execute(sa.text(sql))


def upgrade() -> None:
    specs = (
        ("qms_audits", ("amo_id", "status"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_read ON qms_audits (amo_id, status)"),
        ("qms_audits", ("amo_id", "planned_start"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_read ON qms_audits (amo_id, planned_start) WHERE planned_start IS NOT NULL"),
        ("qms_audits", ("amo_id", "planned_end"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_read ON qms_audits (amo_id, planned_end) WHERE planned_end IS NOT NULL"),
        ("quality_cars", ("amo_id", "due_date", "status"), "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_status_read ON quality_cars (amo_id, due_date, status) WHERE due_date IS NOT NULL"),
        ("qms_audit_findings", ("amo_id", "closed_at"), "CREATE INDEX IF NOT EXISTS ix_qms_findings_amo_closed_read ON qms_audit_findings (amo_id, closed_at)"),
        ("training_records", ("amo_id", "user_id", "course_id", "valid_until", "completion_date"), "CREATE INDEX IF NOT EXISTS ix_training_records_amo_valid_user_course_read ON training_records (amo_id, user_id, course_id, valid_until DESC, completion_date DESC)"),
    )
    for table_name, columns, sql in specs:
        _exec_if_columns(table_name, columns, sql)


def downgrade() -> None:
    for index_name in (
        "ix_training_records_amo_valid_user_course_read",
        "ix_qms_findings_amo_closed_read",
        "ix_quality_cars_amo_due_status_read",
        "ix_qms_audits_amo_planned_end_read",
        "ix_qms_audits_amo_planned_start_read",
        "ix_qms_audits_amo_status_read",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
