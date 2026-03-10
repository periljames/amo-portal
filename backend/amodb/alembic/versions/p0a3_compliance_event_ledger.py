"""P0 compliance event ledger

Revision ID: p0a3_compliance_event_ledger
Revises: p0a2_quality_amo_id_normalization
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "p0a3_compliance_event_ledger"
down_revision = "p0a2_quality_amo_id_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_event_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("prev_hash_sha256", sa.String(length=64), nullable=True),
        sa.Column("signature_alg", sa.String(length=32), nullable=True),
        sa.Column("signature_value", sa.Text(), nullable=True),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_event_ledger_amo_occurred", "compliance_event_ledger", ["amo_id", "occurred_at"])
    op.create_index("ix_compliance_event_ledger_amo_entity_occurred", "compliance_event_ledger", ["amo_id", "entity_type", "entity_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_compliance_event_ledger_amo_entity_occurred", table_name="compliance_event_ledger")
    op.drop_index("ix_compliance_event_ledger_amo_occurred", table_name="compliance_event_ledger")
    op.drop_table("compliance_event_ledger")
