"""Restore QMS calendar performance and preserve canonical QMS styling support.

Revision ID: phase2_5_20260605
Revises: phase2_4_20260605
Create Date: 2026-06-05

Index creation is guarded by the complete referenced-column contract because
this branch can precede tenant-normalisation migrations on clean databases.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_5_20260605"
down_revision = "phase2_4_20260605"
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
        ("qms_audits", ("amo_id", "planned_start", "id"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_start_fast ON qms_audits (amo_id, planned_start ASC NULLS LAST, id) WHERE planned_start IS NOT NULL"),
        ("qms_audits", ("amo_id", "planned_end", "id"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_calendar_end_fast ON qms_audits (amo_id, planned_end ASC NULLS LAST, id) WHERE planned_end IS NOT NULL"),
        ("qms_audits", ("amo_id", "created_at", "id"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_desc_nullslast ON qms_audits (amo_id, created_at DESC NULLS LAST, id)"),
        ("quality_cars", ("amo_id", "due_date", "id"), "CREATE INDEX IF NOT EXISTS ix_quality_cars_calendar_due_fast ON quality_cars (amo_id, due_date ASC NULLS LAST, id) WHERE due_date IS NOT NULL"),
        ("training_events", ("amo_id", "starts_on", "id"), "CREATE INDEX IF NOT EXISTS ix_training_events_calendar_start_fast ON training_events (amo_id, starts_on ASC NULLS LAST, id) WHERE starts_on IS NOT NULL"),
        ("training_records", ("amo_id", "user_id", "course_id", "valid_until", "completion_date", "created_at"), "CREATE INDEX IF NOT EXISTS ix_training_records_latest_currency_fast ON training_records (amo_id, user_id, course_id, valid_until DESC NULLS LAST, completion_date DESC NULLS LAST, created_at DESC NULLS LAST)"),
    )
    for table_name, columns, sql in specs:
        _execute_if_columns(table_name, columns, sql)
    for table_name in ("qms_audits", "quality_cars", "training_events", "training_records"):
        if _columns(table_name):
            op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for index_name in (
        "ix_training_records_latest_currency_fast",
        "ix_training_events_calendar_start_fast",
        "ix_quality_cars_calendar_due_fast",
        "ix_cars_calendar_due_fast",
        "ix_qms_audits_amo_created_desc_nullslast",
        "ix_qms_audits_calendar_end_fast",
        "ix_qms_audits_calendar_start_fast",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
