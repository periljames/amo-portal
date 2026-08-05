"""repair foundation timestamp and effective-date server defaults

Revision ID: foundation_20260805_timestamp_defaults
Revises: rel_20260804_calc_revisions
Create Date: 2026-08-05

The original shared-foundations migration created several NOT NULL columns
without database defaults, while the ORM models declare server defaults. The
ORM therefore omits those values on INSERT and PostgreSQL rejects otherwise
valid base, alias and assignment records.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "foundation_20260805_timestamp_defaults"
down_revision: Union[str, Sequence[str], None] = "rel_20260804_calc_revisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _set_timestamp_default(table_name: str, column_name: str) -> None:
    if column_name not in _columns(table_name):
        return
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def _drop_timestamp_default(table_name: str, column_name: str) -> None:
    if column_name not in _columns(table_name):
        return
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=None,
    )


def upgrade() -> None:
    _set_timestamp_default("base_stations", "created_at")
    _set_timestamp_default("base_stations", "updated_at")
    _set_timestamp_default("base_station_aliases", "created_at")
    _set_timestamp_default("user_base_assignments", "created_at")
    _set_timestamp_default("user_base_assignments", "updated_at")

    if "effective_from" in _columns("user_base_assignments"):
        op.alter_column(
            "user_base_assignments",
            "effective_from",
            existing_type=sa.Date(),
            existing_nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        )


def downgrade() -> None:
    if "effective_from" in _columns("user_base_assignments"):
        op.alter_column(
            "user_base_assignments",
            "effective_from",
            existing_type=sa.Date(),
            existing_nullable=False,
            server_default=None,
        )

    _drop_timestamp_default("user_base_assignments", "updated_at")
    _drop_timestamp_default("user_base_assignments", "created_at")
    _drop_timestamp_default("base_station_aliases", "created_at")
    _drop_timestamp_default("base_stations", "updated_at")
    _drop_timestamp_default("base_stations", "created_at")
