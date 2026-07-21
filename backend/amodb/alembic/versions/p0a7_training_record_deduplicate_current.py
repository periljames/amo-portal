"""Deduplicate current training records and enforce one active record per user/course.

Revision ID: p0a7_train_record_dedupe
Revises: p0a6_train_record
Create Date: 2026-06-08 00:00:00.000000

This migration is idempotent and PostgreSQL-focused. It retains historical records by
marking older active records as RENEWED. It does not delete training evidence.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "p0a7_train_record_dedupe"
down_revision = "p0a6_train_record"
branch_labels = None
depends_on = None

TABLE_NAME = "training_records"
UNIQUE_ACTIVE_INDEX = "uq_training_records_one_active_user_course"
IDX_RENEWED_BY = "idx_training_records_superseded_by"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_exists(column_name: str) -> bool:
    if not _table_exists(TABLE_NAME):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(TABLE_NAME))


def _index_exists(index_name: str) -> bool:
    if not _table_exists(TABLE_NAME):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(TABLE_NAME))


def _ensure_lifecycle_columns() -> None:
    if not _column_exists("record_status"):
        op.add_column(TABLE_NAME, sa.Column("record_status", sa.String(length=64), nullable=True))
    if not _column_exists("source_status"):
        op.add_column(TABLE_NAME, sa.Column("source_status", sa.String(length=64), nullable=True))
    if not _column_exists("superseded_by_record_id"):
        op.add_column(TABLE_NAME, sa.Column("superseded_by_record_id", sa.String(length=36), nullable=True))
    if not _column_exists("superseded_at"):
        op.add_column(TABLE_NAME, sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("purge_after"):
        op.add_column(TABLE_NAME, sa.Column("purge_after", sa.Date(), nullable=True))


def upgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    _ensure_lifecycle_columns()

    # Mark older active records as renewed, keeping only the latest active record per user/course.
    # The latest record is selected by completion_date, then created_at, then id for deterministic ordering.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    FIRST_VALUE(id) OVER (
                        PARTITION BY amo_id, user_id, course_id
                        ORDER BY completion_date DESC, created_at DESC, id DESC
                    ) AS keeper_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY amo_id, user_id, course_id
                        ORDER BY completion_date DESC, created_at DESC, id DESC
                    ) AS rn
                FROM training_records
                WHERE COALESCE(UPPER(record_status), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED')
            )
            UPDATE training_records AS tr
            SET
                record_status = 'RENEWED',
                source_status = COALESCE(NULLIF(tr.source_status, ''), 'RENEWED'),
                superseded_by_record_id = ranked.keeper_id,
                superseded_at = COALESCE(tr.superseded_at, NOW()),
                remarks = CASE
                    WHEN tr.remarks IS NULL OR BTRIM(tr.remarks) = '' THEN 'LifecycleStatus=RENEWED'
                    WHEN tr.remarks !~* '(^|\\|)\\s*LifecycleStatus\\s*=' THEN tr.remarks || ' | LifecycleStatus=RENEWED'
                    ELSE tr.remarks
                END
            FROM ranked
            WHERE tr.id = ranked.id
              AND ranked.rn > 1;
            """
        )
    )

    if not _index_exists(IDX_RENEWED_BY) and _column_exists("superseded_by_record_id"):
        op.create_index(IDX_RENEWED_BY, TABLE_NAME, ["superseded_by_record_id"], unique=False)

    # Enforce one visible/current training record per user/course.
    # Historical records remain in the table because their record_status is RENEWED/SUPERSEDED.
    if not _index_exists(UNIQUE_ACTIVE_INDEX):
        op.execute(
            sa.text(
                f"""
                CREATE UNIQUE INDEX {UNIQUE_ACTIVE_INDEX}
                ON training_records (amo_id, user_id, course_id)
                WHERE COALESCE(UPPER(record_status), 'ACTIVE') NOT IN ('RENEWED', 'SUPERSEDED');
                """
            )
        )


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    if _index_exists(UNIQUE_ACTIVE_INDEX):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {UNIQUE_ACTIVE_INDEX}"))
    if _index_exists(IDX_RENEWED_BY):
        op.drop_index(IDX_RENEWED_BY, table_name=TABLE_NAME)
