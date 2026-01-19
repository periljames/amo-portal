"""merge import heads

Revision ID: 8e1ae4ea5206
Revises: 8b7c1f0a9c2d, 3a1d2f1b6c4f
Create Date: 2025-01-15 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8e1ae4ea5206"
down_revision: Union[str, Sequence[str], None] = ("8b7c1f0a9c2d", "3a1d2f1b6c4f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
