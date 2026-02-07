"""merge heads

Revision ID: e41af43f2beb
Revises: 2c4d7e9f0a1b, 4c2d5e6f8a9b, a5c1d2e3f4b6, c6a9f2d1e7ab, f8a1b2c3d4e6
Create Date: 2026-01-29 08:04:48.748683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e41af43f2beb'
down_revision: Union[str, Sequence[str], None] = ('2c4d7e9f0a1b', '4c2d5e6f8a9b', 'a5c1d2e3f4b6', 'c6a9f2d1e7ab', 'f8a1b2c3d4e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
