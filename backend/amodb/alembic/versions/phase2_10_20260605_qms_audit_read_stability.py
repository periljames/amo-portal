"""QMS audit dashboard and calendar read stability indexes.

Revision ID: phase2_10_20260605
Revises: phase2_9_20260605
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op

revision = "phase2_10_20260605"
down_revision = "phase2_9_20260605"
branch_labels = None
depends_on = None


def _exec_if_table(table: str, sql: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.{table}') IS NOT NULL THEN
            EXECUTE {sql!r};
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _exec_if_table(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_read ON qms_audits (amo_id, status)",
    )
    _exec_if_table(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_read ON qms_audits (amo_id, planned_start) WHERE planned_start IS NOT NULL",
    )
    _exec_if_table(
        "qms_audits",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_read ON qms_audits (amo_id, planned_end) WHERE planned_end IS NOT NULL",
    )
    _exec_if_table(
        "quality_cars",
        "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_status_read ON quality_cars (amo_id, due_date, status) WHERE due_date IS NOT NULL",
    )
    _exec_if_table(
        "qms_audit_findings",
        "CREATE INDEX IF NOT EXISTS ix_qms_findings_amo_closed_read ON qms_audit_findings (amo_id, closed_at)",
    )
    _exec_if_table(
        "training_records",
        "CREATE INDEX IF NOT EXISTS ix_training_records_amo_valid_user_course_read ON training_records (amo_id, user_id, course_id, valid_until DESC, completion_date DESC)",
    )


def downgrade() -> None:
    for index_name in [
        "ix_training_records_amo_valid_user_course_read",
        "ix_qms_findings_amo_closed_read",
        "ix_quality_cars_amo_due_status_read",
        "ix_qms_audits_amo_planned_end_read",
        "ix_qms_audits_amo_planned_start_read",
        "ix_qms_audits_amo_status_read",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
