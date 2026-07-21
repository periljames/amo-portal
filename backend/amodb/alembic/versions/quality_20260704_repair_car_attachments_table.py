"""Repair missing CAR attachment table.

Revision ID: qual_20260704_carattach
Revises: qual_20260704_schedfix
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "qual_20260704_carattach"
down_revision: Union[str, Sequence[str], None] = "qual_20260704_schedfix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(bind, table_name: str, column_name: str, column: sa.Column) -> None:
    if _column_exists(bind, table_name, column_name):
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "quality_car_attachments"):
        op.create_table(
            "quality_car_attachments",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("car_id", sa.UUID(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("file_ref", sa.String(length=512), nullable=False),
            sa.Column("content_type", sa.String(length=128), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    else:
        _add_column_if_missing(bind, "quality_car_attachments", "id", sa.Column("id", sa.UUID(), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "car_id", sa.Column("car_id", sa.UUID(), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "filename", sa.Column("filename", sa.String(length=255), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "file_ref", sa.Column("file_ref", sa.String(length=512), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "content_type", sa.Column("content_type", sa.String(length=128), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "size_bytes", sa.Column("size_bytes", sa.Integer(), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "sha256", sa.Column("sha256", sa.String(length=64), nullable=True))
        _add_column_if_missing(bind, "quality_car_attachments", "uploaded_at", sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    op.execute("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_id_runtime ON quality_car_attachments (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_car_runtime ON quality_car_attachments (car_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_sha_runtime ON quality_car_attachments (sha256)")


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "quality_car_attachments"):
        return
    op.execute("DROP INDEX IF EXISTS ix_quality_car_attachments_sha_runtime")
    op.execute("DROP INDEX IF EXISTS ix_quality_car_attachments_car_runtime")
    op.execute("DROP INDEX IF EXISTS ix_quality_car_attachments_id_runtime")
    op.drop_table("quality_car_attachments")
