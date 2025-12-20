"""add lockout count to users

Revision ID: 8b7c1f0a9c2d
Revises: f4c7f0c1d2ab
Create Date: 2025-02-14 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b7c1f0a9c2d"
down_revision: Union[str, Sequence[str], None] = "f4c7f0c1d2ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "lockout_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("users", "lockout_count", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "lockout_count")
