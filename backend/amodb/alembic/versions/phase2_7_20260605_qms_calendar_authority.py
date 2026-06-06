"""QMS calendar authoritative date and visibility indexes.

Revision ID: phase2_7_20260605
Revises: phase2_6_20260605
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "phase2_7_20260605"
down_revision = "phase2_6_20260605"
branch_labels = None
depends_on = None


def _relation_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return bool(bind.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar())


def _execute_if_exists(table_name: str, sql: str) -> None:
    if _relation_exists(table_name):
        op.execute(sql)


def upgrade() -> None:
    _execute_if_exists(
        "qms_audits",
        """
        CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_fast
        ON qms_audits (amo_id, planned_start, id)
        WHERE planned_start IS NOT NULL
        """,
    )
    _execute_if_exists(
        "qms_audits",
        """
        CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_fast
        ON qms_audits (amo_id, planned_end, id)
        WHERE planned_end IS NOT NULL
        """,
    )
    _execute_if_exists(
        "training_records",
        """
        CREATE INDEX IF NOT EXISTS ix_training_records_latest_user_course_fast
        ON training_records (amo_id, user_id, course_id, valid_until DESC NULLS LAST, completion_date DESC NULLS LAST, created_at DESC)
        """,
    )
    _execute_if_exists(
        "users",
        """
        CREATE INDEX IF NOT EXISTS ix_users_amo_id_display_fast
        ON users (amo_id, id)
        INCLUDE (full_name, email, staff_code)
        """,
    )
    for table_name in ("qms_audits", "training_records", "users"):
        _execute_if_exists(table_name, f"ANALYZE {table_name}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_amo_id_display_fast")
    op.execute("DROP INDEX IF EXISTS ix_training_records_latest_user_course_fast")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_planned_end_fast")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_planned_start_fast")
