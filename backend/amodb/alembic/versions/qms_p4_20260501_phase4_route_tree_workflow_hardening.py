"""phase 4 QMS route tree and workflow hardening

Revision ID: qms_p4_20260501
Revises: qms_p3_20260501
Create Date: 2026-05-01

Adds columns used by the canonical QMS activity log and file/evidence security
surfaces. This migration is additive and safe to run on databases where the
tables already exist or where Phase 2 created the generic canonical tables.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "qms_p4_20260501"
down_revision = "qms_p3_20260501"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(
            bind.execute(sa.text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"})
            .scalar()
        )
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    if _is_postgresql():
        return bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).first()
        )
    return any(col["name"] == column_name for col in sa.inspect(bind).get_columns(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _table_exists(table_name) and not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_postgres(index_name: str, table_name: str, columns: str) -> None:
    if _is_postgresql() and _table_exists(table_name):
        op.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})")


def upgrade() -> None:
    if _table_exists("qms_activity_logs"):
        _add_column_if_missing("qms_activity_logs", sa.Column("actor_user_id", sa.String(length=36), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("action", sa.String(length=96), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("module", sa.String(length=96), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("entity_type", sa.String(length=96), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("entity_id", sa.String(length=64), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("previous_value", postgresql.JSONB() if _is_postgresql() else sa.JSON(), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("new_value", postgresql.JSONB() if _is_postgresql() else sa.JSON(), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("ip_address", sa.String(length=96), nullable=True))
        _add_column_if_missing("qms_activity_logs", sa.Column("user_agent", sa.Text(), nullable=True))
        _create_index_if_postgres("ix_qms_activity_logs_actor", "qms_activity_logs", "amo_id, actor_user_id")
        _create_index_if_postgres("ix_qms_activity_logs_entity", "qms_activity_logs", "amo_id, entity_type, entity_id")
        _create_index_if_postgres("ix_qms_activity_logs_action", "qms_activity_logs", "amo_id, action")

    if _table_exists("qms_file_access_logs"):
        _add_column_if_missing("qms_file_access_logs", sa.Column("actor_user_id", sa.String(length=36), nullable=True))
        _add_column_if_missing("qms_file_access_logs", sa.Column("file_id", sa.String(length=64), nullable=True))
        _add_column_if_missing("qms_file_access_logs", sa.Column("action", sa.String(length=64), nullable=True))
        _add_column_if_missing("qms_file_access_logs", sa.Column("ip_address", sa.String(length=96), nullable=True))
        _add_column_if_missing("qms_file_access_logs", sa.Column("user_agent", sa.Text(), nullable=True))
        _create_index_if_postgres("ix_qms_file_access_logs_file", "qms_file_access_logs", "amo_id, file_id")
        _create_index_if_postgres("ix_qms_file_access_logs_actor", "qms_file_access_logs", "amo_id, actor_user_id")


def downgrade() -> None:
    # Keep audit/file security columns. They are additive and may contain audit evidence.
    pass
