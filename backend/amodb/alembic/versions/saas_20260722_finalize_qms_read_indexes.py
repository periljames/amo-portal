"""Finalize QMS and Training read indexes after schema convergence.

Revision ID: saas_20260722_qms_read_idx
Revises: saas_20260722_finalize_training
Create Date: 2026-07-22

The historical read-stability branch is intentionally column-aware because it
can run before tenant-normalisation migrations. This terminal revision runs
after the SaaS, Quality, Training, Workforce, and core rostering chains have
converged and guarantees every required dashboard/calendar index exists.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "saas_20260722_qms_read_idx"
down_revision = "saas_20260722_finalize_training"
branch_labels = None
depends_on = None


INDEX_SPECS = (
    (
        "qms_audits",
        ("amo_id", "status", "id"),
        "ix_qms_audits_amo_status_id",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_status_id ON qms_audits (amo_id, status, id)",
    ),
    (
        "qms_audits",
        ("amo_id", "planned_start", "id"),
        "ix_qms_audits_amo_planned_start_id",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_start_id ON qms_audits (amo_id, planned_start, id) WHERE planned_start IS NOT NULL",
    ),
    (
        "qms_audits",
        ("amo_id", "planned_end", "id"),
        "ix_qms_audits_amo_planned_end_id",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_planned_end_id ON qms_audits (amo_id, planned_end, id) WHERE planned_end IS NOT NULL",
    ),
    (
        "qms_audits",
        ("amo_id", "created_at", "id"),
        "ix_qms_audits_amo_created_id",
        "CREATE INDEX IF NOT EXISTS ix_qms_audits_amo_created_id ON qms_audits (amo_id, created_at DESC, id)",
    ),
    (
        "quality_cars",
        ("amo_id", "status", "id"),
        "ix_quality_cars_amo_status_id",
        "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_status_id ON quality_cars (amo_id, status, id)",
    ),
    (
        "quality_cars",
        ("amo_id", "due_date", "id"),
        "ix_quality_cars_amo_due_id",
        "CREATE INDEX IF NOT EXISTS ix_quality_cars_amo_due_id ON quality_cars (amo_id, due_date, id) WHERE due_date IS NOT NULL",
    ),
    (
        "qms_audit_findings",
        ("amo_id", "closed_at", "id"),
        "ix_qms_findings_amo_closed_id",
        "CREATE INDEX IF NOT EXISTS ix_qms_findings_amo_closed_id ON qms_audit_findings (amo_id, closed_at, id)",
    ),
    (
        "qms_documents",
        ("amo_id", "status", "id"),
        "ix_qms_documents_amo_status_id",
        "CREATE INDEX IF NOT EXISTS ix_qms_documents_amo_status_id ON qms_documents (amo_id, status, id)",
    ),
    (
        "training_records",
        ("amo_id", "user_id", "course_id", "completion_date", "created_at", "id"),
        "ix_training_records_amo_user_course_latest",
        "CREATE INDEX IF NOT EXISTS ix_training_records_amo_user_course_latest ON training_records (amo_id, user_id, course_id, completion_date DESC, created_at DESC, id DESC)",
    ),
    (
        "training_records",
        ("amo_id", "valid_until", "id"),
        "ix_training_records_amo_valid_until_id",
        "CREATE INDEX IF NOT EXISTS ix_training_records_amo_valid_until_id ON training_records (amo_id, valid_until, id) WHERE valid_until IS NOT NULL",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    missing: list[str] = []

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
