"""QMS calendar authoritative date and visibility indexes.

Revision ID: phase2_7_20260605
Revises: phase2_6_20260605
Create Date: 2026-06-05

Historical index creation is guarded by every referenced column so this branch
remains safe before tenant-normalisation migrations have completed.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_7_20260605"
down_revision = "phase2_6_20260605"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _execute_if_columns(table_name: str, columns: Iterable[str], sql: str) -> None:
    if set(columns).issubset(_columns(table_name)):
        op.execute(sa.text(sql))


def upgrade() -> None:
    specs = (
        (
            "qms_audits",
            ("amo_id", "planned_start", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_fast ON qms_audits (amo_id, planned_start, id) WHERE planned_start IS NOT NULL",
        ),
        (
            "qms_audits",
            ("amo_id", "planned_end", "id"),
            "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_fast ON qms_audits (amo_id, planned_end, id) WHERE planned_end IS NOT NULL",
        ),
        (
            "training_records",
            ("amo_id", "user_id", "course_id", "valid_until", "completion_date", "created_at"),
            "CREATE INDEX IF NOT EXISTS ix_training_records_latest_user_course_fast ON training_records (amo_id, user_id, course_id, valid_until DESC NULLS LAST, completion_date DESC NULLS LAST, created_at DESC)",
        ),
        (
            "users",
            ("amo_id", "id", "full_name", "email", "staff_code"),
            "CREATE INDEX IF NOT EXISTS ix_users_amo_id_display_fast ON users (amo_id, id) INCLUDE (full_name, email, staff_code)",
        ),
    )
    for table_name, columns, sql in specs:
        _execute_if_columns(table_name, columns, sql)
    for table_name in ("qms_audits", "training_records", "users"):
        if _columns(table_name):
            op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for index_name in (
        "ix_users_amo_id_display_fast",
        "ix_training_records_latest_user_course_fast",
        "ix_qms_audits_amo_planned_end_fast",
        "ix_qms_audits_amo_planned_start_fast",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
