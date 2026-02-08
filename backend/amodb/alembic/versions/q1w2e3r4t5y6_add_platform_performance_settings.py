"""add platform performance settings

Revision ID: q1w2e3r4t5y6
Revises: n1b2c3d4e5f9
Create Date: 2026-02-06 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "q1w2e3r4t5y6"
down_revision: Union[str, Sequence[str], None] = "n1b2c3d4e5f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("platform_settings"):
        return
    existing_columns = {column["name"] for column in inspector.get_columns("platform_settings")}

    if "gzip_minimum_size" not in existing_columns:
        op.add_column("platform_settings", sa.Column("gzip_minimum_size", sa.Integer(), nullable=True))
    if "gzip_compresslevel" not in existing_columns:
        op.add_column("platform_settings", sa.Column("gzip_compresslevel", sa.Integer(), nullable=True))
    if "max_request_body_bytes" not in existing_columns:
        op.add_column("platform_settings", sa.Column("max_request_body_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("platform_settings"):
        return
    existing_columns = {column["name"] for column in inspector.get_columns("platform_settings")}

    if "max_request_body_bytes" in existing_columns:
        op.drop_column("platform_settings", "max_request_body_bytes")
    if "gzip_compresslevel" in existing_columns:
        op.drop_column("platform_settings", "gzip_compresslevel")
    if "gzip_minimum_size" in existing_columns:
        op.drop_column("platform_settings", "gzip_minimum_size")
