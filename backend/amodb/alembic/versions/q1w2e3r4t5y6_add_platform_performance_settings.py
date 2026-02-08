"""add platform performance settings

Revision ID: q1w2e3r4t5y6
Revises: n1b2c3d4e5f9
Create Date: 2026-02-06 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "q1w2e3r4t5y6"
down_revision: Union[str, Sequence[str], None] = "n1b2c3d4e5f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("gzip_minimum_size", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("gzip_compresslevel", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("max_request_body_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_settings", "max_request_body_bytes")
    op.drop_column("platform_settings", "gzip_compresslevel")
    op.drop_column("platform_settings", "gzip_minimum_size")
