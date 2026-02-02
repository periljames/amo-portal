"""merge heads after EHM and platform settings updates

Revision ID: j1k2l3m4n5o6
Revises: 2c4d7e9f0a1b, 4c2d5e6f8a9b, a5c1d2e3f4b6, c6a9f2d1e7ab, h1e2m3l4o5g6
Create Date: 2026-02-05 00:00:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, Sequence[str], None] = (
    "2c4d7e9f0a1b",
    "4c2d5e6f8a9b",
    "a5c1d2e3f4b6",
    "c6a9f2d1e7ab",
    "h1e2m3l4o5g6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
