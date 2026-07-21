"""QMS dashboard/calendar read stability indexes.

Revision ID: qms_20260607_read_stability
Revises: None
Create Date: 2026-06-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "qms_20260607_read_stability"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    row = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).first()
    return row is not None


def _create_if_table(bind, table_name: str, sql: str) -> None:
    if _table_exists(bind, table_name):
        op.execute(sql)


def upgrade() -> None:
    bind = op.get_bind()
    _create_if_table(bind, "qms_audits", "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_id ON qms_audits (amo_id, status, id)")
    _create_if_table(bind, "qms_audits", "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_id ON qms_audits (amo_id, planned_start, id) WHERE planned_start IS NOT NULL")
    _create_if_table(bind, "qms_audits", "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_id ON qms_audits (amo_id, planned_end, id) WHERE planned_end IS NOT NULL")
    _create_if_table(bind, "qms_audits", "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_id ON qms_audits (amo_id, created_at DESC, id)")
    _create_if_table(bind, "quality_cars", "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_status_id ON quality_cars (amo_id, status, id)")
    _create_if_table(bind, "quality_cars", "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_id ON quality_cars (amo_id, due_date, id) WHERE due_date IS NOT NULL")
    _create_if_table(bind, "qms_audit_findings", "CREATE INDEX IF NOT EXISTS ix_qms_findings_amo_closed_id ON qms_audit_findings (amo_id, closed_at, id)")
    _create_if_table(bind, "qms_documents", "CREATE INDEX IF NOT EXISTS ix_qms_documents_amo_status_id ON qms_documents (amo_id, status, id)")
    _create_if_table(bind, "training_records", "CREATE INDEX IF NOT EXISTS ix_training_records_amo_user_course_latest ON training_records (amo_id, user_id, course_id, completion_date DESC, created_at DESC, id DESC)")
    _create_if_table(bind, "training_records", "CREATE INDEX IF NOT EXISTS ix_training_records_amo_valid_until_id ON training_records (amo_id, valid_until, id) WHERE valid_until IS NOT NULL")
    for table_name in ("qms_audits", "quality_cars", "qms_audit_findings", "qms_documents", "training_records"):
        if _table_exists(bind, table_name):
            op.execute(sa.text(f"ANALYZE {table_name}"))


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
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
