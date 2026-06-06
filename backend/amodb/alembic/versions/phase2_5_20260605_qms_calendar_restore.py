"""Restore QMS calendar performance and preserve canonical QMS styling support.

Revision ID: phase2_5_20260605
Revises: phase2_4_20260605
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "phase2_5_20260605"
down_revision = "phase2_4_20260605"
branch_labels = None
depends_on = None


def _relation_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return bool(bind.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar())


def _execute_if_table_exists(table_name: str, sql: str) -> None:
    if _relation_exists(table_name):
        op.execute(sql)


def upgrade() -> None:
    _execute_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_start_fast ON qms_audits (amo_id, planned_start ASC NULLS LAST, id) WHERE planned_start IS NOT NULL",
    )
    _execute_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_end_fast ON qms_audits (amo_id, planned_end ASC NULLS LAST, id) WHERE planned_end IS NOT NULL",
    )
    _execute_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_desc_nullslast ON qms_audits (amo_id, created_at DESC NULLS LAST, id)",
    )
    _execute_if_table_exists(
        "quality_cars",
        "CREATE INDEX IF NOT EXISTS ix_quality_cars_calendar_due_fast ON quality_cars (amo_id, due_date ASC NULLS LAST, id) WHERE due_date IS NOT NULL",
    )
    _execute_if_table_exists(
        "training_events",
        "CREATE INDEX IF NOT EXISTS ix_training_events_calendar_start_fast ON training_events (amo_id, starts_on ASC NULLS LAST, id) WHERE starts_on IS NOT NULL",
    )
    _execute_if_table_exists(
        "training_records",
        "CREATE INDEX IF NOT EXISTS ix_training_records_latest_currency_fast ON training_records (amo_id, user_id, course_id, valid_until DESC NULLS LAST, completion_date DESC NULLS LAST, created_at DESC NULLS LAST)",
    )
    for table_name in ("qms_audits", "quality_cars", "training_events", "training_records"):
        _execute_if_table_exists(table_name, f"ANALYZE {table_name}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_training_records_latest_currency_fast")
    op.execute("DROP INDEX IF EXISTS ix_training_events_calendar_start_fast")
    op.execute("DROP INDEX IF EXISTS ix_quality_cars_calendar_due_fast")
    op.execute("DROP INDEX IF EXISTS ix_cars_calendar_due_fast")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_created_desc_nullslast")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_calendar_end_fast")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_calendar_start_fast")
