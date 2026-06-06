"""QMS calendar performance and training currency integrity indexes.

Revision ID: phase2_4_20260605
Revises: s9t8u7v6w5x4
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "phase2_4_20260605"
down_revision = "s9t8u7v6w5x4"
branch_labels = None
depends_on = None


def _relation_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return bool(bind.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar())


def _create_index_if_table_exists(table_name: str, sql: str) -> None:
    if _relation_exists(table_name):
        op.execute(sql)


def _analyze_if_table_exists(table_name: str) -> None:
    if _relation_exists(table_name):
        op.execute(f"ANALYZE {table_name}")


def upgrade() -> None:
    _create_index_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start ON qms_audits (amo_id, planned_start) WHERE planned_start IS NOT NULL",
    )
    _create_index_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end ON qms_audits (amo_id, planned_end) WHERE planned_end IS NOT NULL",
    )
    _create_index_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_id ON qms_audits (amo_id, created_at DESC, id)",
    )
    _create_index_if_table_exists(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_created ON qms_audits (amo_id, status, created_at DESC)",
    )
    _create_index_if_table_exists(
        "quality_cars",
        "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_status ON quality_cars (amo_id, due_date, status) WHERE due_date IS NOT NULL",
    )
    _create_index_if_table_exists(
        "training_events",
        "CREATE INDEX IF NOT EXISTS ix_training_events_amo_starts_status ON training_events (amo_id, starts_on, status) WHERE starts_on IS NOT NULL",
    )
    _create_index_if_table_exists(
        "training_events",
        "CREATE INDEX IF NOT EXISTS ix_training_events_amo_ends_status ON training_events (amo_id, ends_on, status) WHERE ends_on IS NOT NULL",
    )
    _create_index_if_table_exists(
        "training_records",
        "CREATE INDEX IF NOT EXISTS ix_training_records_currency_latest ON training_records (amo_id, user_id, course_id, valid_until DESC, completion_date DESC, created_at DESC)",
    )
    for table_name in ("qms_audits", "quality_cars", "training_events", "training_records"):
        _analyze_if_table_exists(table_name)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_training_records_currency_latest")
    op.execute("DROP INDEX IF EXISTS ix_training_events_amo_ends_status")
    op.execute("DROP INDEX IF EXISTS ix_training_events_amo_starts_status")
    op.execute("DROP INDEX IF EXISTS ix_quality_cars_amo_due_status")
    op.execute("DROP INDEX IF EXISTS ix_cars_amo_due_status")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_status_created")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_created_id")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_planned_end")
    op.execute("DROP INDEX IF EXISTS ix_qms_audits_amo_planned_start")
