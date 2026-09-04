"""Widen audit-event correlation IDs for governed workflow trace keys.

Revision ID: audit_260903_corr_255
Revises: quality_260903_officer_ae
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "audit_260903_corr_255"
down_revision = "quality_260903_officer_ae"
branch_labels = None
depends_on = None


TABLE = "audit_events"
COLUMN = "correlation_id"


def _column(bind) -> dict | None:
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return None
    return next(
        (column for column in inspector.get_columns(TABLE) if column["name"] == COLUMN),
        None,
    )


def upgrade() -> None:
    bind = op.get_bind()
    column = _column(bind)
    if column is None:
        return
    current_length = getattr(column["type"], "length", None)
    if current_length is not None and current_length >= 255:
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column(
            COLUMN,
            existing_type=column["type"],
            type_=sa.String(length=255),
            existing_nullable=column.get("nullable", True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    column = _column(bind)
    if column is None:
        return
    current_length = getattr(column["type"], "length", None)
    if current_length is not None and current_length <= 64:
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.alter_column(
            COLUMN,
            existing_type=column["type"],
            type_=sa.String(length=64),
            existing_nullable=column.get("nullable", True),
        )
