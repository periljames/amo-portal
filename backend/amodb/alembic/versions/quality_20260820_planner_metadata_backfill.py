"""Backfill authoritative Planner metadata for pre-existing audit schedules.

Revision ID: quality_260820_planner_backfill
Revises: quality_260820_provider_gov, procurement_260820_supplier_gov
Create Date: 2026-08-20

This migration is intentionally data-preserving. Existing schedule identity,
frequency, scope, ownership and dates remain untouched; only the metadata row
required by the authoritative Planner lifecycle is added where absent. It also
joins the two governance heads already present on main so the repository returns
to one exact Alembic head.
"""
from __future__ import annotations

from datetime import timedelta
import uuid

from alembic import op
import sqlalchemy as sa


revision = "quality_260820_planner_backfill"
down_revision = (
    "quality_260820_provider_gov",
    "procurement_260820_supplier_gov",
)
branch_labels = None
depends_on = None

_MIGRATION_NOTE = (
    "Migrated from the pre-authoritative audit schedule API. "
    "The source record was date-based and did not store a governed start time."
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("qms_audit_schedules") or not inspector.has_table("qms_planner_schedule_metadata"):
        return

    rows = bind.execute(
        sa.text(
            """
            SELECT
                s.id,
                s.amo_id,
                s.next_due_date,
                s.duration_days,
                s.is_active,
                s.lead_auditor_user_id,
                s.created_by_user_id,
                s.created_at,
                COALESCE(NULLIF(a.time_zone, ''), 'UTC') AS timezone_name
            FROM qms_audit_schedules s
            JOIN amos a ON a.id = s.amo_id
            LEFT JOIN qms_planner_schedule_metadata m
              ON m.amo_id = s.amo_id
             AND m.schedule_id = s.id
            WHERE s.deleted_at IS NULL
              AND m.id IS NULL
            ORDER BY s.amo_id, s.next_due_date, s.id
            """
        )
    ).mappings().all()

    for row in rows:
        start_date = row["next_due_date"]
        if start_date is None:
            continue
        duration_days = max(int(row["duration_days"] or 1), 1)
        metadata_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO qms_planner_schedule_metadata (
                    id,
                    amo_id,
                    schedule_id,
                    occurrence_date,
                    end_date,
                    start_time,
                    end_time,
                    timezone_name,
                    location,
                    notes,
                    responsible_user_id,
                    attendee_user_ids_json,
                    external_attendees_json,
                    notify_attendees,
                    lifecycle_status,
                    version,
                    created_by_user_id,
                    updated_by_user_id,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :amo_id,
                    :schedule_id,
                    :occurrence_date,
                    :end_date,
                    NULL,
                    NULL,
                    :timezone_name,
                    NULL,
                    :notes,
                    :responsible_user_id,
                    '[]',
                    '[]',
                    TRUE,
                    :lifecycle_status,
                    1,
                    :created_by_user_id,
                    :updated_by_user_id,
                    COALESCE(:created_at, CURRENT_TIMESTAMP),
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": metadata_id,
                "amo_id": row["amo_id"],
                "schedule_id": row["id"],
                "occurrence_date": start_date,
                "end_date": start_date + timedelta(days=duration_days - 1),
                "timezone_name": row["timezone_name"] or "UTC",
                "notes": _MIGRATION_NOTE,
                "responsible_user_id": row["lead_auditor_user_id"],
                "lifecycle_status": "ACTIVE" if bool(row["is_active"]) else "SUSPENDED",
                "created_by_user_id": row["created_by_user_id"],
                "updated_by_user_id": row["created_by_user_id"],
                "created_at": row["created_at"],
            },
        )


def downgrade() -> None:
    # Do not destroy authoritative metadata on downgrade. Rows may have acquired
    # later versioned changes after this migration ran, so deleting them would
    # lose governed schedule history.
    pass
