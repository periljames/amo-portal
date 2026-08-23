"""Widen shared usage-meter counters for governed AI accounting.

Revision ID: ai_meter_bigint_260823
Revises: 1b2c3d4e6f70
Create Date: 2026-08-23

AI provider-cost meters are stored in micro-USD and token counters are cumulative.
Both can legitimately exceed PostgreSQL's 32-bit integer range, so the shared
usage-meter value column must use BIGINT before tenant AI billing is enabled.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ai_meter_bigint_260823"
down_revision = "1b2c3d4e6f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "usage_meters",
        "used_units",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "usage_meters",
        "used_units",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="used_units::integer",
    )
