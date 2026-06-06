"""phase2.2 qms and training performance indexes

Revision ID: phase2_2_20260605
Revises: phase1_20260604
Create Date: 2026-06-05
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


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(bind.execute(sa.text("SELECT to_regclass(:name)"), {"name": f"public.{table_name}"}).scalar())
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname = :index_name
                    """
                ),
                {"index_name": index_name},
            ).first()
        )
    for table in sa.inspect(bind).get_table_names():
        if any(idx.get("name") == index_name for idx in sa.inspect(bind).get_indexes(table)):
            return True
    return False


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _table_exists(table_name) or _index_exists(index_name):
        return
    op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    _create_index_if_missing("ix_qms_audits_amo_status", "qms_audits", ["amo_id", "status"])
    _create_index_if_missing("ix_qms_audits_amo_planned_status", "qms_audits", ["amo_id", "planned_start", "status"])
    _create_index_if_missing("ix_quality_cars_amo_status", "quality_cars", ["amo_id", "status"])
    _create_index_if_missing("ix_quality_cars_amo_due_status", "quality_cars", ["amo_id", "due_date", "status"])
    _create_index_if_missing("ix_qms_documents_amo_status", "qms_documents", ["amo_id", "status"])
    _create_index_if_missing("ix_qms_findings_amo_closed", "qms_audit_findings", ["amo_id", "closed_at"])
    _create_index_if_missing("ix_training_records_amo_valid_until", "training_records", ["amo_id", "valid_until"])
    _create_index_if_missing("ix_training_records_amo_user_course", "training_records", ["amo_id", "user_id", "course_id"])
    _create_index_if_missing("ix_training_events_amo_dates_status", "training_events", ["amo_id", "starts_on", "ends_on", "status"])
    _create_index_if_missing("ix_training_requirements_amo_active_scope", "training_requirements", ["amo_id", "is_active", "scope"])


def downgrade() -> None:
    for index_name, table_name in [
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
    ]:
        if _table_exists(table_name) and _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)
