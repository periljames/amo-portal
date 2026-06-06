"""QMS calendar visibility and source diagnostics indexes.

Revision ID: phase2_6_20260605
Revises: phase2_5_20260605
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "phase2_6_20260605"
down_revision = "phase2_5_20260605"
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
        CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_start_cover_v2
        ON qms_audits (amo_id, planned_start, id)
        INCLUDE (audit_ref, title, status, kind, planned_end, lead_auditor_user_id)
        WHERE planned_start IS NOT NULL
        """,
    )
    _execute_if_exists(
        "qms_audits",
        """
        CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_end_cover_v2
        ON qms_audits (amo_id, planned_end, id)
        INCLUDE (audit_ref, title, status, kind, planned_start, lead_auditor_user_id)
        WHERE planned_end IS NOT NULL
        """,
    )
    _execute_if_exists(
        "qms_audits",
        """
        CREATE INDEX IF NOT EXISTS ix_qms_audits_dashboard_status_v2
        ON qms_audits (amo_id, status, planned_start, created_at DESC)
        """,
    )
    _execute_if_exists(
        "quality_cars",
        """
        CREATE INDEX IF NOT EXISTS ix_quality_cars_calendar_due_cover_v2
        ON quality_cars (amo_id, due_date, id)
        INCLUDE (car_number, title, status, priority, closed_at)
        WHERE due_date IS NOT NULL
        """,
    )
    _execute_if_exists(
        "training_events",
        """
        CREATE INDEX IF NOT EXISTS ix_training_events_calendar_start_cover_v2
        ON training_events (amo_id, starts_on, id)
        INCLUDE (title, status, ends_on, course_id)
        WHERE starts_on IS NOT NULL
        """,
    )
    _execute_if_exists(
        "training_records",
        """
        CREATE INDEX IF NOT EXISTS ix_training_records_calendar_valid_latest_v2
        ON training_records (amo_id, valid_until, user_id, course_id, id)
        INCLUDE (completion_date, created_at)
        WHERE valid_until IS NOT NULL
        """,
    )
    for table_name in ("qms_audits", "quality_cars", "training_events", "training_records"):
        _execute_if_exists(table_name, f"ANALYZE {table_name}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_training_records_calendar_valid_latest_v2")
    op.execute("DROP INDEX IF EXISTS ix_training_events_calendar_start_cover_v2")
    op.execute("DROP INDEX IF EXISTS ix_quality_cars_calendar_due_cover_v2")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_dashboard_status_v2")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_calendar_end_cover_v2")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_calendar_start_cover_v2")
