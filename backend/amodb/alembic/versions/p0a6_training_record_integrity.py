"""P0 training record integrity fields

Revision ID: p0a6_train_record
Revises: p0a5_train_plan
Create Date: 2026-04-09 00:10:00.000000

This migration is intentionally idempotent. Some production/staging databases
already contain part or all of these columns from earlier manual/schema-sync
runs while the Alembic revision was not stamped. Plain ``op.add_column`` then
fails with DuplicateColumn and blocks all later QMS migrations.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p0a6_train_record"
down_revision = "p0a5_train_plan"
branch_labels = None
depends_on = None


TABLE_NAME = "training_records"
FK_NAME = "fk_training_records_superseded_by"
IDX_AMO_STATUS = "idx_training_records_amo_status"
IDX_PURGE_AFTER = "idx_training_records_purge_after"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(fk.get("name") == constraint_name for fk in _inspector().get_foreign_keys(table_name))


def _add_column_if_missing(column: sa.Column) -> None:
    if not _column_exists(TABLE_NAME, column.name):
        op.add_column(TABLE_NAME, column)


def _drop_column_if_exists(column_name: str) -> None:
    if _column_exists(TABLE_NAME, column_name):
        op.drop_column(TABLE_NAME, column_name)


def _create_index_if_missing(index_name: str, columns: list[str]) -> None:
    if all(_column_exists(TABLE_NAME, column) for column in columns) and not _index_exists(TABLE_NAME, index_name):
        op.create_index(index_name, TABLE_NAME, columns)


def _drop_index_if_exists(index_name: str) -> None:
    if _index_exists(TABLE_NAME, index_name):
        op.drop_index(index_name, table_name=TABLE_NAME)


def upgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    _add_column_if_missing(sa.Column("legacy_record_id", sa.String(length=64), nullable=True))
    _add_column_if_missing(sa.Column("source_status", sa.String(length=64), nullable=True))
    _add_column_if_missing(sa.Column("record_status", sa.String(length=64), nullable=True))
    _add_column_if_missing(sa.Column("superseded_by_record_id", sa.String(length=36), nullable=True))
    _add_column_if_missing(sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(sa.Column("purge_after", sa.Date(), nullable=True))

    if (
        _column_exists(TABLE_NAME, "superseded_by_record_id")
        and _column_exists(TABLE_NAME, "id")
        and not _foreign_key_exists(TABLE_NAME, FK_NAME)
    ):
        op.create_foreign_key(
            FK_NAME,
            TABLE_NAME,
            TABLE_NAME,
            ["superseded_by_record_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _create_index_if_missing(IDX_AMO_STATUS, ["amo_id", "record_status"])
    _create_index_if_missing(IDX_PURGE_AFTER, ["purge_after"])


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    _drop_index_if_exists(IDX_PURGE_AFTER)
    _drop_index_if_exists(IDX_AMO_STATUS)

    if _foreign_key_exists(TABLE_NAME, FK_NAME):
        op.drop_constraint(FK_NAME, TABLE_NAME, type_="foreignkey")

    _drop_column_if_exists("purge_after")
    _drop_column_if_exists("superseded_at")
    _drop_column_if_exists("superseded_by_record_id")
    _drop_column_if_exists("record_status")
    _drop_column_if_exists("source_status")
    _drop_column_if_exists("legacy_record_id")
