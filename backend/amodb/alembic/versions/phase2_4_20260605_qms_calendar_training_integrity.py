"""QMS calendar performance and training currency integrity indexes.

Revision ID: phase2_4_20260605
Revises: s9t8u7v6w5x4
Create Date: 2026-06-05

This branch can execute before tenant-normalisation branches, so index creation
must require every referenced column rather than only the table name.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_4_20260605"
down_revision = "s9t8u7v6w5x4"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _create_index_if_columns(table_name: str, columns: Iterable[str], sql: str) -> None:
    if set(columns).issubset(_columns(table_name)):
        op.execute(sa.text(sql))


def _analyze_if_table_exists(table_name: str) -> None:
    if _columns(table_name):
        op.execute(sa.text(f'ANALYZE "{table_name}"'))


def upgrade() -> None:
    specs = (
        ("qms_audits", ("amo_id", "planned_start"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start ON qms_audits (amo_id, planned_start) WHERE planned_start IS NOT NULL"),
        ("qms_audits", ("amo_id", "planned_end"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end ON qms_audits (amo_id, planned_end) WHERE planned_end IS NOT NULL"),
        ("qms_audits", ("amo_id", "created_at", "id"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_id ON qms_audits (amo_id, created_at DESC, id)"),
        ("qms_audits", ("amo_id", "status", "created_at"), "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_created ON qms_audits (amo_id, status, created_at DESC)"),
        ("quality_cars", ("amo_id", "due_date", "status"), "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_status ON quality_cars (amo_id, due_date, status) WHERE due_date IS NOT NULL"),
        ("training_events", ("amo_id", "starts_on", "status"), "CREATE INDEX IF NOT EXISTS ix_training_events_amo_starts_status ON training_events (amo_id, starts_on, status) WHERE starts_on IS NOT NULL"),
        ("training_events", ("amo_id", "ends_on", "status"), "CREATE INDEX IF NOT EXISTS ix_training_events_amo_ends_status ON training_events (amo_id, ends_on, status) WHERE ends_on IS NOT NULL"),
        ("training_records", ("amo_id", "user_id", "course_id", "valid_until", "completion_date", "created_at"), "CREATE INDEX IF NOT EXISTS ix_training_records_currency_latest ON training_records (amo_id, user_id, course_id, valid_until DESC, completion_date DESC, created_at DESC)"),
    )
    for table_name, columns, sql in specs:
        _create_index_if_columns(table_name, columns, sql)
    for table_name in ("qms_audits", "quality_cars", "training_events", "training_records"):
        _analyze_if_table_exists(table_name)


def downgrade() -> None:
    for index_name in (
        "ix_training_records_currency_latest",
        "ix_training_events_amo_ends_status",
        "ix_training_events_amo_starts_status",
        "ix_quality_cars_amo_due_status",
        "ix_cars_amo_due_status",
        "ix_qms_audits_amo_status_created",
        "ix_qms_audits_amo_created_id",
        "ix_qms_audits_amo_planned_end",
        "ix_qms_audits_amo_planned_start",
    ):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
