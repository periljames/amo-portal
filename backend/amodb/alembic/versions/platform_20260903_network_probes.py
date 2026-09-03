"""platform network probe history for SLA diagnostics

Revision ID: platform_20260903_netprobe
Revises: quality_260902_qms13_gate
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "platform_20260903_netprobe"
down_revision = "quality_260902_qms13_gate"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("platform_network_probes"):
        return
    op.create_table(
        "platform_network_probes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("jitter_ms", sa.Float(), nullable=True),
        sa.Column("download_bps", sa.Float(), nullable=True),
        sa.Column("upload_bps", sa.Float(), nullable=True),
        sa.Column("download_bytes", sa.Integer(), nullable=True),
        sa.Column("upload_bytes", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_platform_network_probes_captured", "platform_network_probes", ["captured_at"])
    op.create_index("ix_platform_network_probes_scenario", "platform_network_probes", ["scenario", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_network_probes_scenario", table_name="platform_network_probes")
    op.drop_index("ix_platform_network_probes_captured", table_name="platform_network_probes")
    op.drop_table("platform_network_probes")
