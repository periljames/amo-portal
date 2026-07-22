"""Finalize canonical QMS and Training read indexes after schema convergence.

Revision ID: saas_20260722_qms_read_idx
Revises: saas_20260722_finalize_training
Create Date: 2026-07-22

Historical Phase 2 branches created overlapping calendar/dashboard indexes and
could execute before tenant-normalisation columns existed. This terminal
revision runs after SaaS, Quality, Training, Workforce, core rostering and all
independent Phase 2 read-index branches. It removes legacy variants and installs
one bounded canonical set.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "saas_20260722_qms_read_idx"
down_revision = "saas_20260722_finalize_training"
branch_labels = None
depends_on = (
    "phase2_8_20260605",
    "phase2_10_20260605",
    "phase2_14_20260615",
)


LEGACY_INDEXES = (
    "ix_qms_audits_amo_status",
    "ix_qms_audits_amo_planned_status",
    "ix_quality_cars_amo_status",
    "ix_quality_cars_amo_due_status",
    "ix_qms_documents_amo_status",
    "ix_qms_findings_amo_closed",
    "ix_training_records_amo_valid_until",
    "ix_training_records_amo_user_course",
    "ix_training_events_amo_dates_status",
    "ix_qms_audits_dashboard_open_partial",
    "ix_qms_audits_dashboard_in_progress_partial",
    "ix_qms_audits_dashboard_due_partial",
    "ix_quality_cars_dashboard_open_partial",
    "ix_quality_cars_dashboard_due_partial",
    "ix_qms_findings_dashboard_open_partial",
    "ix_training_records_dashboard_expired_partial",
    "ix_qms_audits_amo_planned_start",
    "ix_qms_audits_amo_planned_end",
    "ix_qms_audits_amo_status_created",
    "ix_training_events_amo_starts_status",
    "ix_training_events_amo_ends_status",
    "ix_training_records_currency_latest",
    "ix_qms_audits_calendar_start_fast",
    "ix_qms_audits_calendar_end_fast",
    "ix_qms_audits_amo_created_desc_nullslast",
    "ix_quality_cars_calendar_due_fast",
    "ix_training_events_calendar_start_fast",
    "ix_training_records_latest_currency_fast",
    "ix_qms_audits_calendar_start_cover_v2",
    "ix_qms_audits_calendar_end_cover_v2",
    "ix_qms_audits_dashboard_status_v2",
    "ix_quality_cars_calendar_due_cover_v2",
    "ix_training_events_calendar_start_cover_v2",
    "ix_training_records_calendar_valid_latest_v2",
    "ix_qms_audits_amo_planned_start_fast",
    "ix_qms_audits_amo_planned_end_fast",
    "ix_training_records_latest_user_course_fast",
    "ix_users_amo_id_display_fast",
    "ix_qms_audits_amo_status_fast",
    "ix_quality_cars_amo_due_status_fast",
    "ix_qms_audit_findings_amo_open_fast",
    "ix_training_records_amo_latest_calendar",
    "ix_training_events_amo_start_status_fast",
    "ix_qms_audits_amo_status_read",
    "ix_qms_audits_amo_planned_start_read",
    "ix_qms_audits_amo_planned_end_read",
    "ix_quality_cars_amo_due_status_read",
    "ix_qms_findings_amo_closed_read",
    "ix_training_records_amo_valid_user_course_read",
    "ix_qms_audit_schedules_amo_due_active",
    "ix_qms_findings_amo_closed_target",
    "ix_training_records_amo_valid_until_user_course",
    "ix_training_event_participants_amo_event",
)


INDEX_SPECS = (
    (
        "qms_audits",
        ("amo_id", "status", "id"),
        "ix_qms_audits_amo_status_id",
        "CREATE INDEX ix_qms_audits_amo_status_id ON qms_audits (amo_id, status, id)",
    ),
    (
        "qms_audits",
        ("amo_id", "planned_start", "id"),
        "ix_qms_audits_amo_planned_start_id",
        "CREATE INDEX ix_qms_audits_amo_planned_start_id ON qms_audits (amo_id, planned_start, id) WHERE planned_start IS NOT NULL",
    ),
    (
        "qms_audits",
        ("amo_id", "planned_end", "id"),
        "ix_qms_audits_amo_planned_end_id",
        "CREATE INDEX ix_qms_audits_amo_planned_end_id ON qms_audits (amo_id, planned_end, id) WHERE planned_end IS NOT NULL",
    ),
    (
        "qms_audits",
        ("amo_id", "created_at", "id"),
        "ix_qms_audits_amo_created_id",
        "CREATE INDEX ix_qms_audits_amo_created_id ON qms_audits (amo_id, created_at DESC, id)",
    ),
    (
        "qms_audit_schedules",
        ("amo_id", "next_due_date", "is_active", "id"),
        "ix_qms_audit_schedules_amo_due_active_id",
        "CREATE INDEX ix_qms_audit_schedules_amo_due_active_id ON qms_audit_schedules (amo_id, next_due_date, is_active, id) WHERE next_due_date IS NOT NULL",
    ),
    (
        "quality_cars",
        ("amo_id", "status", "id"),
        "ix_quality_cars_amo_status_id",
        "CREATE INDEX ix_quality_cars_amo_status_id ON quality_cars (amo_id, status, id)",
    ),
    (
        "quality_cars",
        ("amo_id", "due_date", "id"),
        "ix_quality_cars_amo_due_id",
        "CREATE INDEX ix_quality_cars_amo_due_id ON quality_cars (amo_id, due_date, id) WHERE due_date IS NOT NULL",
    ),
    (
        "qms_audit_findings",
        ("amo_id", "closed_at", "id"),
        "ix_qms_findings_amo_closed_id",
        "CREATE INDEX ix_qms_findings_amo_closed_id ON qms_audit_findings (amo_id, closed_at, id)",
    ),
    (
        "qms_audit_findings",
        ("amo_id", "target_close_date", "id"),
        "ix_qms_findings_amo_target_close_id",
        "CREATE INDEX ix_qms_findings_amo_target_close_id ON qms_audit_findings (amo_id, target_close_date, id) WHERE target_close_date IS NOT NULL",
    ),
    (
        "qms_documents",
        ("amo_id", "status", "id"),
        "ix_qms_documents_amo_status_id",
        "CREATE INDEX ix_qms_documents_amo_status_id ON qms_documents (amo_id, status, id)",
    ),
    (
        "training_records",
        ("amo_id", "user_id", "course_id", "valid_until", "completion_date", "created_at", "id"),
        "ix_training_records_amo_user_course_latest",
        "CREATE INDEX ix_training_records_amo_user_course_latest ON training_records (amo_id, user_id, course_id, valid_until DESC NULLS LAST, completion_date DESC, created_at DESC, id DESC)",
    ),
    (
        "training_records",
        ("amo_id", "valid_until", "id"),
        "ix_training_records_amo_valid_until_id",
        "CREATE INDEX ix_training_records_amo_valid_until_id ON training_records (amo_id, valid_until, id) WHERE valid_until IS NOT NULL",
    ),
    (
        "training_events",
        ("amo_id", "starts_on", "id", "title", "status", "ends_on", "course_id"),
        "ix_training_events_amo_starts_id",
        "CREATE INDEX ix_training_events_amo_starts_id ON training_events (amo_id, starts_on, id) INCLUDE (title, status, ends_on, course_id) WHERE starts_on IS NOT NULL",
    ),
    (
        "training_events",
        ("amo_id", "ends_on", "id", "title", "status", "starts_on", "course_id"),
        "ix_training_events_amo_ends_id",
        "CREATE INDEX ix_training_events_amo_ends_id ON training_events (amo_id, ends_on, id) INCLUDE (title, status, starts_on, course_id) WHERE ends_on IS NOT NULL",
    ),
    (
        "training_event_participants",
        ("amo_id", "event_id", "user_id", "id"),
        "ix_training_event_participants_amo_event_user_id",
        "CREATE INDEX ix_training_event_participants_amo_event_user_id ON training_event_participants (amo_id, event_id, user_id, id)",
    ),
    (
        "training_requirements",
        ("amo_id", "is_active", "scope", "course_id"),
        "ix_training_requirements_amo_active_scope_course",
        "CREATE INDEX ix_training_requirements_amo_active_scope_course ON training_requirements (amo_id, is_active, scope, course_id)",
    ),
    (
        "users",
        ("amo_id", "id", "full_name", "email", "staff_code"),
        "ix_users_amo_id_display",
        "CREATE INDEX ix_users_amo_id_display ON users (amo_id, id) INCLUDE (full_name, email, staff_code)",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    missing: list[str] = []

    for index_name in LEGACY_INDEXES:
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    for _table_name, _required_columns, index_name, _sql in INDEX_SPECS:
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))

    for table_name, required_columns, _index_name, sql in INDEX_SPECS:
        if not inspector.has_table(table_name):
            missing.append(f"missing table {table_name}")
            continue
        columns = {str(column["name"]) for column in inspector.get_columns(table_name)}
        absent = sorted(set(required_columns) - columns)
        if absent:
            missing.append(f"{table_name} missing columns {','.join(absent)}")
            continue
        op.execute(sa.text(sql))

    if missing:
        raise RuntimeError(
            "QMS read-index convergence failed: " + "; ".join(sorted(missing))
        )

    for table_name in sorted({spec[0] for spec in INDEX_SPECS}):
        op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for _table_name, _required_columns, index_name, _sql in reversed(INDEX_SPECS):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
