"""Add fast QMS calendar/dashboard integration indexes.

Revision ID: phase2_14_20260615
Revises: phase2_13_20260614
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "phase2_14_20260615"
down_revision = "phase2_13_20260614"
branch_labels = None
depends_on = None


def _create_index_if_table(table: str, sql: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table}') IS NOT NULL THEN
                {sql};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _create_index_if_table(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_status ON qms_audits (amo_id, planned_start, planned_end, status)",
    )
    _create_index_if_table(
        "qms_audit_schedules",
        "CREATE INDEX IF NOT EXISTS ix_qms_audit_schedules_amo_due_active ON qms_audit_schedules (amo_id, next_due_date, is_active)",
    )
    _create_index_if_table(
        "quality_cars",
        "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_status ON quality_cars (amo_id, due_date, status)",
    )
    _create_index_if_table(
        "qms_audit_findings",
        "CREATE INDEX IF NOT EXISTS ix_qms_findings_amo_closed_target ON qms_audit_findings (amo_id, closed_at, target_close_date)",
    )
    _create_index_if_table(
        "training_records",
        "CREATE INDEX IF NOT EXISTS ix_training_records_amo_valid_until_user_course ON training_records (amo_id, valid_until, user_id, course_id)",
    )
    _create_index_if_table(
        "training_events",
        "CREATE INDEX IF NOT EXISTS ix_training_events_amo_starts_status ON training_events (amo_id, starts_on, status)",
    )
    _create_index_if_table(
        "training_event_participants",
        "CREATE INDEX IF NOT EXISTS ix_training_event_participants_amo_event ON training_event_participants (amo_id, event_id)",
    )


def downgrade() -> None:
    for name in [
        "ix_training_event_participants_amo_event",
        "ix_training_events_amo_starts_status",
        "ix_training_records_amo_valid_until_user_course",
        "ix_qms_findings_amo_closed_target",
        "ix_quality_cars_amo_due_status",
        "ix_qms_audit_schedules_amo_due_active",
        "ix_qms_audits_amo_planned_status",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {name}")
