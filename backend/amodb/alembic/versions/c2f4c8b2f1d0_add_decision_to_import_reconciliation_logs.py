"""add decision to import reconciliation logs

Revision ID: c2f4c8b2f1d0
Revises: 70a4e360dd80
Create Date: 2025-12-30 10:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2f4c8b2f1d0"
down_revision: Union[str, Sequence[str], None] = "e1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "aircraft_import_reconciliation_logs",
        sa.Column("decision", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("aircraft_import_reconciliation_logs", "decision")
