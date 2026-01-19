"""add verification status to fleet records

Revision ID: f4c7f0c1d2ab
Revises: c2f4c8b2f1d0
Create Date: 2025-01-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4c7f0c1d2ab"
down_revision: Union[str, Sequence[str], None] = "c2f4c8b2f1d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "aircraft",
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="UNVERIFIED",
        ),
    )
    op.add_column(
        "aircraft_components",
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="UNVERIFIED",
        ),
    )
    op.add_column(
        "aircraft_usage",
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="UNVERIFIED",
        ),
    )
    op.alter_column("aircraft", "verification_status", server_default=None)
    op.alter_column(
        "aircraft_components", "verification_status", server_default=None
    )
    op.alter_column("aircraft_usage", "verification_status", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("aircraft_usage", "verification_status")
    op.drop_column("aircraft_components", "verification_status")
    op.drop_column("aircraft", "verification_status")
