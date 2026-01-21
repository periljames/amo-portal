"""add integration inbound events

Revision ID: f6b7c8d9e0f1
Revises: f5a8b9c1d2e3
Create Date: 2025-01-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "f5a8b9c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_inbound_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("integration_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_integration_inbound_events_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integration_configs.id"],
            name=op.f("fk_integration_inbound_events_integration_id_integration_configs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_integration_inbound_events_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_inbound_events")),
        sa.UniqueConstraint(
            "amo_id",
            "integration_id",
            "idempotency_key",
            name="uq_integration_inbound_amo_integration_idempotency",
        ),
    )
    op.create_index(
        "ix_integration_inbound_amo_integration_received",
        "integration_inbound_events",
        ["amo_id", "integration_id", "received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_amo_id"),
        "integration_inbound_events",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_created_by_user_id"),
        "integration_inbound_events",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_event_type"),
        "integration_inbound_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_idempotency_key"),
        "integration_inbound_events",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_integration_id"),
        "integration_inbound_events",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_payload_hash"),
        "integration_inbound_events",
        ["payload_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_received_at"),
        "integration_inbound_events",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_inbound_events_signature_valid"),
        "integration_inbound_events",
        ["signature_valid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_inbound_events_signature_valid"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_received_at"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_payload_hash"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_integration_id"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_idempotency_key"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_event_type"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_created_by_user_id"), table_name="integration_inbound_events")
    op.drop_index(op.f("ix_integration_inbound_events_amo_id"), table_name="integration_inbound_events")
    op.drop_index("ix_integration_inbound_amo_integration_received", table_name="integration_inbound_events")
    op.drop_table("integration_inbound_events")
