"""Finalize deferred Training planning and record-integrity changes.

Revision ID: saas_20260722_finalize_training
Revises: saas_20260722_finalize_idx
Create Date: 2026-07-22

P0 Training revisions run on a parallel branch and correctly skip tables that
have not been created yet. This terminal convergence migration guarantees that
those fields, constraints and indexes exist once the complete schema graph has
landed. Existing training evidence is retained; older duplicate current records
are marked RENEWED rather than deleted.
"""
from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = "saas_20260722_finalize_training"
down_revision = "saas_20260722_finalize_idx"
branch_labels = None
depends_on = None

COURSE_TABLE = "training_courses"
RECORD_TABLE = "training_records"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {str(column["name"]) for column in _inspector().get_columns(table_name)}


def _has_columns(table_name: str, columns: Iterable[str]) -> bool:
    return set(columns).issubset(_columns(table_name))


def _index_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {
        str(index.get("name"))
        for index in _inspector().get_indexes(table_name)
        if index.get("name")
    }


def _check_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {
        str(item.get("name"))
        for item in _inspector().get_check_constraints(table_name)
        if item.get("name")
    }


def _foreign_key_exists(table_name: str, columns: Iterable[str], referred_table: str) -> bool:
    if not _has_table(table_name):
        return False
    expected = tuple(columns)
    return any(
        tuple(item.get("constrained_columns") or ()) == expected
        and str(item.get("referred_table") or "") == referred_table
        for item in _inspector().get_foreign_keys(table_name)
    )


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _finalize_course_planning() -> None:
    if not _has_table(COURSE_TABLE):
        return

    _add_column_if_missing(COURSE_TABLE, sa.Column("nominal_hours", sa.Integer(), nullable=True))
    _add_column_if_missing(
        COURSE_TABLE,
        sa.Column("planning_lead_days", sa.Integer(), nullable=True, server_default=sa.text("45")),
    )
    _add_column_if_missing(
        COURSE_TABLE,
        sa.Column("candidate_requirement_text", sa.Text(), nullable=True),
    )

    checks = _check_names(COURSE_TABLE)
    if "nominal_hours" in _columns(COURSE_TABLE) and "ck_training_course_nominal_hours_nonneg" not in checks:
        op.create_check_constraint(
            "ck_training_course_nominal_hours_nonneg",
            COURSE_TABLE,
            "nominal_hours IS NULL OR nominal_hours >= 0",
        )
    checks = _check_names(COURSE_TABLE)
    if "planning_lead_days" in _columns(COURSE_TABLE) and "ck_training_course_planning_lead_nonneg" not in checks:
        op.create_check_constraint(
            "ck_training_course_planning_lead_nonneg",
            COURSE_TABLE,
            "planning_lead_days IS NULL OR planning_lead_days >= 0",
        )


def _finalize_record_columns() -> None:
    if not _has_table(RECORD_TABLE):
        return

    for column in (
        sa.Column("legacy_record_id", sa.String(length=64), nullable=True),
        sa.Column("source_status", sa.String(length=64), nullable=True),
        sa.Column("record_status", sa.String(length=64), nullable=True),
        sa.Column("superseded_by_record_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.Date(), nullable=True),
    ):
        _add_column_if_missing(RECORD_TABLE, column)

    if (
        _has_columns(RECORD_TABLE, ("id", "superseded_by_record_id"))
        and not _foreign_key_exists(RECORD_TABLE, ("superseded_by_record_id",), RECORD_TABLE)
    ):
        op.create_foreign_key(
            "fk_training_records_superseded_by",
            RECORD_TABLE,
            RECORD_TABLE,
            ["superseded_by_record_id"],
            ["id"],
            ondelete="SET NULL",
        )

    for name, columns in (
        ("idx_training_records_amo_status", ("amo_id", "record_status")),
        ("idx_training_records_purge_after", ("purge_after",)),
        ("idx_training_records_superseded_by", ("superseded_by_record_id",)),
    ):
        if _has_columns(RECORD_TABLE, columns) and name not in _index_names(RECORD_TABLE):
            op.create_index(name, RECORD_TABLE, list(columns))


def _deduplicate_current_records() -> None:
    required = (
        "id",
        "amo_id",
        "user_id",
        "course_id",
        "completion_date",
        "created_at",
        "record_status",
        "source_status",
        "superseded_by_record_id",
        "superseded_at",
    )
    if not _has_columns(RECORD_TABLE, required):
        return

    remarks_assignment = ""
    if "remarks" in _columns(RECORD_TABLE):
        remarks_assignment = """,
                remarks = CASE
                    WHEN tr.remarks IS NULL OR BTRIM(tr.remarks) = '' THEN 'LifecycleStatus=RENEWED'
                    WHEN tr.remarks !~* '(^|\\|)\\s*LifecycleStatus\\s*=' THEN tr.remarks || ' | LifecycleStatus=RENEWED'
                    ELSE tr.remarks
                END"""

    op.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT
                    id,
                    FIRST_VALUE(id) OVER (
                        PARTITION BY amo_id, user_id, course_id
                        ORDER BY completion_date DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                    ) AS keeper_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY amo_id, user_id, course_id
                        ORDER BY completion_date DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                    ) AS rn
                FROM training_records
                WHERE COALESCE(UPPER(record_status), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')
            )
            UPDATE training_records AS tr
            SET
                record_status = 'RENEWED',
                source_status = COALESCE(NULLIF(tr.source_status, ''), 'RENEWED'),
                superseded_by_record_id = ranked.keeper_id,
                superseded_at = COALESCE(tr.superseded_at, NOW())
                {remarks_assignment}
            FROM ranked
            WHERE tr.id = ranked.id
              AND ranked.rn > 1
            """
        )
    )

    unique_name = "uq_training_records_one_active_user_course"
    if unique_name not in _index_names(RECORD_TABLE):
        op.execute(
            sa.text(
                f"""
                CREATE UNIQUE INDEX {unique_name}
                ON training_records (amo_id, user_id, course_id)
                WHERE COALESCE(UPPER(record_status), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')
                """
            )
        )


def upgrade() -> None:
    _finalize_course_planning()
    _finalize_record_columns()
    _deduplicate_current_records()


def downgrade() -> None:
    # This is a non-destructive convergence repair. Earlier P0 revisions own the
    # individual columns and indexes, so reversing them here could remove schema
    # that existed before this finalizer ran.
    pass
