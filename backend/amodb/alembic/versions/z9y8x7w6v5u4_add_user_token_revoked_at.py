"""add user token revoked at

Revision ID: z9y8x7w6v5u4
Revises: q1w2e3r4t5y6
Create Date: 2026-02-10 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "z9y8x7w6v5u4"
down_revision = "q1w2e3r4t5y6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "token_revoked_at")
