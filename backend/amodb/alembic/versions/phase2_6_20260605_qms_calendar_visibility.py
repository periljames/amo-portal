"""QMS calendar visibility and source diagnostics indexes.

Revision ID: phase2_6_20260605
Revises: phase2_5_20260605
Create Date: 2026-06-05

Covering indexes are created only when all key and INCLUDE columns exist. This
keeps the historical branch safe when it executes before tenant normalisation.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_6_20260605"
down_revision = "phase2_5_20260605"
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
            ("amo_id", "planned_start", "id", "audit_ref", "title", "status", "kind", "planned_end", "lead_auditor_user_id"),
            """
            CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_start_cover_v2
            ON qms_audits (amo_id, planned_start, id)
            INCLUDE (audit_ref, title, status, kind, planned_end, lead_auditor_user_id)
            WHERE planned_start IS NOT NULL
            """,
        ),
        (
            "qms_audits",
            ("amo_id", "planned_end", "id", "audit_ref", "title", "status", "kind", "planned_start", "lead_auditor_user_id"),
            """
            CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_end_cover_v2
            ON qms_audits (amo_id, planned_end, id)
            INCLUDE (audit_ref, title, status, kind, planned_start, lead_auditor_user_id)
            WHERE planned_end IS NOT NULL
            """,
        ),
        (
            "qms_audits",
            ("amo_id", "status", "planned_start", "created_at"),
            """
            CREATE INDEX IF NOT EXISTS ix_qms_audits_dashboard_status_v2
            ON qms_audits (amo_id, status, planned_start, created_at DESC)
            """,
        ),
        (
            "quality_cars",
            ("amo_id", "due_date", "id", "car_number", "title", "status", "priority", "closed_at"),
            """
            CREATE INDEX IF NOT EXISTS ix_quality_cars_calendar_due_cover_v2
            ON quality_cars (amo_id, due_date, id)
            INCLUDE (car_number, title, status, priority, closed_at)
            WHERE due_date IS NOT NULL
            """,
        ),
        (
            "training_events",
            ("amo_id", "starts_on", "id", "title", "status", "ends_on", "course_id"),
            """
            CREATE INDEX IF NOT EXISTS ix_training_events_calendar_start_cover_v2
            ON training_events (amo_id, starts_on, id)
            INCLUDE (title, status, ends_on, course_id)
            WHERE starts_on IS NOT NULL
            """,
        ),
        (
            "training_records",
            ("amo_id", "valid_until", "user_id", "course_id", "id", "completion_date", "created_at"),
            """
            CREATE INDEX IF NOT EXISTS ix_training_records_calendar_valid_latest_v2
            ON training_records (amo_id, valid_until, user_id, course_id, id)
            INCLUDE (completion_date, created_at)
            WHERE valid_until IS NOT NULL
            """,
        ),
    )
    for table_name, columns, sql in specs:
        _execute_if_columns(table_name, columns, sql)
    for table_name in ("qms_audits", "quality_cars", "training_events", "training_records"):
        if _columns(table_name):
            op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for index_name in (
        "ix_training_records_calendar_valid_latest_v2",
        "ix_training_events_calendar_start_cover_v2",
        "ix_quality_cars_calendar_due_cover_v2",
        "ix_qms_audits_dashboard_status_v2",
        "ix_qms_audits_calendar_end_cover_v2",
        "ix_qms_audits_calendar_start_cover_v2",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
