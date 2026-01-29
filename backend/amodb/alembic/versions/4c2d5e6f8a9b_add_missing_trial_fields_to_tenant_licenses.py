"""add missing trial fields to tenant_licenses

Revision ID: 4c2d5e6f8a9b
Revises: e3f1a2b3c4d5
Create Date: 2025-02-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4c2d5e6f8a9b"
down_revision: Union[str, Sequence[str], None] = "e3f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_licenses",
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_licenses",
        sa.Column("trial_grace_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_licenses",
        sa.Column(
            "is_read_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("tenant_licenses", "is_read_only", server_default=None)


def downgrade() -> None:
    op.drop_column("tenant_licenses", "is_read_only")
    op.drop_column("tenant_licenses", "trial_grace_expires_at")
    op.drop_column("tenant_licenses", "trial_started_at")
