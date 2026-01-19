"""Add must_change_password flag to users.

Revision ID: d2f8c9a1b4e7
Revises: 1b2c3d4e6f70
Create Date: 2025-02-21 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d2f8c9a1b4e7"
down_revision: Union[str, Sequence[str], None] = "1b2c3d4e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute(
        "UPDATE users SET must_change_password = FALSE WHERE last_login_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
