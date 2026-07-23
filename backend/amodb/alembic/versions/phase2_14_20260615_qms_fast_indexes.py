"""Add fast QMS calendar/dashboard integration indexes.

Revision ID: phase2_14_20260615
Revises: phase2_13_20260614
Create Date: 2026-06-15

This historical branch can execute while Quality and Training tables are only
partially shaped by parallel migrations. Every index is therefore guarded by
its complete referenced-column contract.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa

revision = "phase2_14_20260615"
down_revision = "phase2_13_20260614"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname = :index_name
                    """
                ),
                {"index_name": index_name},
            ).first()
        )
    return any(
        index.get("name") == index_name
        for table_name in sa.inspect(bind).get_table_names()
        for index in sa.inspect(bind).get_indexes(table_name)
    )


def _create_index_if_columns(
    index_name: str,
    table_name: str,
    columns: list[str],
    required_columns: Iterable[str] = (),
) -> None:
    required = set(columns) | set(required_columns)
    if not required.issubset(_columns(table_name)) or _index_exists(index_name):
        return
    op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    for index_name, table_name, columns in (
        ("ix_qms_audits_amo_planned_status", "qms_audits", ["amo_id", "planned_start", "planned_end", "status"]),
        ("ix_qms_audit_schedules_amo_due_active", "qms_audit_schedules", ["amo_id", "next_due_date", "is_active"]),
        ("ix_quality_cars_amo_due_status", "quality_cars", ["amo_id", "due_date", "status"]),
        ("ix_qms_findings_amo_closed_target", "qms_audit_findings", ["amo_id", "closed_at", "target_close_date"]),
        ("ix_training_records_amo_valid_until_user_course", "training_records", ["amo_id", "valid_until", "user_id", "course_id"]),
        ("ix_training_events_amo_starts_status", "training_events", ["amo_id", "starts_on", "status"]),
        ("ix_training_event_participants_amo_event", "training_event_participants", ["amo_id", "event_id"]),
    ):
        _create_index_if_columns(index_name, table_name, columns)


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_training_event_participants_amo_event", "training_event_participants"),
        ("ix_training_events_amo_starts_status", "training_events"),
        ("ix_training_records_amo_valid_until_user_course", "training_records"),
        ("ix_qms_findings_amo_closed_target", "qms_audit_findings"),
        ("ix_quality_cars_amo_due_status", "quality_cars"),
        ("ix_qms_audit_schedules_amo_due_active", "qms_audit_schedules"),
        ("ix_qms_audits_amo_planned_status", "qms_audits"),
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)
