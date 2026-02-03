"""add catalog sku usage limits

Revision ID: l1b2c3d4e5f7
Revises: k1b2c3d4e5f6
Create Date: 2026-02-03 07:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "l1b2c3d4e5f7"
down_revision = "k1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_skus", sa.Column("min_usage_limit", sa.Integer(), nullable=True))
    op.add_column("catalog_skus", sa.Column("max_usage_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_skus", "max_usage_limit")
    op.drop_column("catalog_skus", "min_usage_limit")
