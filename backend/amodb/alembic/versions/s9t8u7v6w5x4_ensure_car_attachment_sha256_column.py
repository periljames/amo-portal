"""ensure car attachment sha256 column

Revision ID: s9t8u7v6w5x4
Revises: z1y2x3w4v5u6
Create Date: 2026-02-10 07:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "s9t8u7v6w5x4"
down_revision = "z1y2x3w4v5u6"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "quality_car_attachments"
    index_name = op.f("ix_quality_car_attachments_sha256")

    if not _has_table(inspector, table_name):
        return

    if not _has_column(inspector, table_name, "sha256"):
        op.add_column(table_name, sa.Column("sha256", sa.String(length=64), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, ["sha256"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "quality_car_attachments"
    index_name = op.f("ix_quality_car_attachments_sha256")

    if not _has_table(inspector, table_name):
        return

    if _has_index(inspector, table_name, index_name):
        op.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    if _has_column(inspector, table_name, "sha256"):
        op.drop_column(table_name, "sha256")
