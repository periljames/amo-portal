"""Reconcile TrainingRecord.updated_at with the authoritative database schema.

Revision ID: training_260820_record_updated
Revises: training_260818_policy_merge
Create Date: 2026-08-20

The ORM has long treated ``training_records.updated_at`` as a non-null timestamp,
but the historical Training migration chain never created the column.  Fresh
PostgreSQL environments therefore fail as soon as SQLAlchemy loads a TrainingRecord.
This migration is additive and idempotent so deployed databases that already carry
the runtime column are left unchanged.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_260820_record_updated"
down_revision = "training_260818_policy_merge"
branch_labels = None
depends_on = None

TABLE = "training_records"
COLUMN = "updated_at"


def _columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN in _columns() or not _columns():
        return

    # A server-side default makes the operation data-preserving for existing rows
    # and keeps fresh-database inserts valid even outside the SQLAlchemy ORM.
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # This is a schema-reconciliation migration.  Some deployed databases may have
    # acquired the column before Alembic tracked it, so a destructive downgrade
    # could remove valid production data.  Preserve the reconciled column.
    pass
