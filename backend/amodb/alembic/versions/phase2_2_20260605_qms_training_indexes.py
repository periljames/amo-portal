"""Phase 2.2 QMS and Training performance indexes.

Revision ID: phase2_2_20260605
Revises: phase1_20260604
Create Date: 2026-06-05

This branch can see partially-created Quality and Training tables from other
Alembic heads. Indexes are created only when every referenced column exists.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "phase2_2_20260605"
down_revision = "phase1_20260604"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname = :index_name
                    """
                ),
                {"index_name": index_name},
            ).first()
        )
    for table_name in sa.inspect(bind).get_table_names():
        if any(index.get("name") == index_name for index in sa.inspect(bind).get_indexes(table_name)):
            return True
    return False


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not set(columns).issubset(_columns(table_name)) or _index_exists(index_name):
        return
    op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    for index_name, table_name, columns in (
        ("ix_qms_audits_amo_status", "qms_audits", ["amo_id", "status"]),
        ("ix_qms_audits_amo_planned_status", "qms_audits", ["amo_id", "planned_start", "status"]),
        ("ix_quality_cars_amo_status", "quality_cars", ["amo_id", "status"]),
        ("ix_quality_cars_amo_due_status", "quality_cars", ["amo_id", "due_date", "status"]),
        ("ix_qms_documents_amo_status", "qms_documents", ["amo_id", "status"]),
        ("ix_qms_findings_amo_closed", "qms_audit_findings", ["amo_id", "closed_at"]),
        ("ix_training_records_amo_valid_until", "training_records", ["amo_id", "valid_until"]),
        ("ix_training_records_amo_user_course", "training_records", ["amo_id", "user_id", "course_id"]),
        ("ix_training_events_amo_dates_status", "training_events", ["amo_id", "starts_on", "ends_on", "status"]),
        ("ix_training_requirements_amo_active_scope", "training_requirements", ["amo_id", "is_active", "scope"]),
    ):
        _create_index_if_missing(index_name, table_name, columns)


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_training_requirements_amo_active_scope", "training_requirements"),
        ("ix_training_events_amo_dates_status", "training_events"),
        ("ix_training_records_amo_user_course", "training_records"),
        ("ix_training_records_amo_valid_until", "training_records"),
        ("ix_qms_findings_amo_closed", "qms_audit_findings"),
        ("ix_qms_documents_amo_status", "qms_documents"),
        ("ix_quality_cars_amo_due_status", "quality_cars"),
        ("ix_quality_cars_amo_status", "quality_cars"),
        ("ix_qms_audits_amo_planned_status", "qms_audits"),
        ("ix_qms_audits_amo_status", "qms_audits"),
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)
