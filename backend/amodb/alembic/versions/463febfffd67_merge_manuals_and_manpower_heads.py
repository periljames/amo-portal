"""merge manuals and manpower heads

Revision ID: 463febfffd67
Revises: m2n3u4a5l6s7, a1b2c3d4e5f6
Create Date: 2026-02-19 18:28:42.001251

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '463febfffd67'
down_revision: Union[str, Sequence[str], None] = ('m2n3u4a5l6s7', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
