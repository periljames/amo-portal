"""add mergeable route latency histograms

Revision ID: saas_20260731_route_latency_hist
Revises: qual_20260704_scopes
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "saas_20260731_route_latency_hist"
down_revision: Union[str, Sequence[str], None] = "qual_20260704_scopes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "platform_route_latency_histograms_1m"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _has_table(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("is_platform_route", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "histogram_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("min_duration_ms", sa.Float(), nullable=True),
        sa.Column("max_duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_route_latency_hist_bucket",
        TABLE_NAME,
        ["bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_platform_route_latency_hist_route",
        TABLE_NAME,
        ["route", "bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_platform_route_latency_hist_tenant",
        TABLE_NAME,
        ["tenant_id", "bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    if _has_table(TABLE_NAME):
        op.drop_table(TABLE_NAME)
