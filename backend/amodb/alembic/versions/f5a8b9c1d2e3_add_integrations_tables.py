"""add integrations tables

Revision ID: f5a8b9c1d2e3
Revises: f4c7f0c1d2ab
Create Date: 2025-01-12 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5a8b9c1d2e3"
down_revision: Union[str, Sequence[str], None] = "f4c7f0c1d2ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("integration_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "DISABLED", name="integration_config_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("signing_secret", sa.String(length=255), nullable=True),
        sa.Column("allowed_ips", sa.Text(), nullable=True),
        sa.Column("credentials_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_integration_configs_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_integration_configs_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_integration_configs_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_configs")),
        sa.UniqueConstraint("amo_id", "integration_key", name="uq_integration_configs_amo_key"),
    )
    op.create_index(
        "ix_integration_configs_amo_key",
        "integration_configs",
        ["amo_id", "integration_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_configs_amo_id"),
        "integration_configs",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_configs_enabled"),
        "integration_configs",
        ["enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_configs_integration_key"),
        "integration_configs",
        ["integration_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_configs_status"),
        "integration_configs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "integration_outbound_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("integration_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SENT",
                "FAILED",
                "DEAD_LETTER",
                name="integration_outbound_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_integration_outbound_events_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integration_configs.id"],
            name=op.f("fk_integration_outbound_events_integration_id_integration_configs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_integration_outbound_events_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_outbound_events")),
        sa.UniqueConstraint(
            "amo_id",
            "idempotency_key",
            name="uq_integration_outbound_amo_idempotency",
        ),
    )
    op.create_index(
        "ix_integration_outbound_amo_status",
        "integration_outbound_events",
        ["amo_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_integration_outbound_next_attempt_at",
        "integration_outbound_events",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_integration_outbound_created_at",
        "integration_outbound_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_integration_outbound_amo_integration",
        "integration_outbound_events",
        ["amo_id", "integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbound_events_amo_id"),
        "integration_outbound_events",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbound_events_event_type"),
        "integration_outbound_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbound_events_idempotency_key"),
        "integration_outbound_events",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbound_events_integration_id"),
        "integration_outbound_events",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbound_events_status"),
        "integration_outbound_events",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_outbound_events_status"), table_name="integration_outbound_events")
    op.drop_index(op.f("ix_integration_outbound_events_integration_id"), table_name="integration_outbound_events")
    op.drop_index(op.f("ix_integration_outbound_events_idempotency_key"), table_name="integration_outbound_events")
    op.drop_index(op.f("ix_integration_outbound_events_event_type"), table_name="integration_outbound_events")
    op.drop_index(op.f("ix_integration_outbound_events_amo_id"), table_name="integration_outbound_events")
    op.drop_index("ix_integration_outbound_amo_integration", table_name="integration_outbound_events")
    op.drop_index("ix_integration_outbound_created_at", table_name="integration_outbound_events")
    op.drop_index("ix_integration_outbound_next_attempt_at", table_name="integration_outbound_events")
    op.drop_index("ix_integration_outbound_amo_status", table_name="integration_outbound_events")
    op.drop_table("integration_outbound_events")

    op.drop_index(op.f("ix_integration_configs_status"), table_name="integration_configs")
    op.drop_index(op.f("ix_integration_configs_integration_key"), table_name="integration_configs")
    op.drop_index(op.f("ix_integration_configs_enabled"), table_name="integration_configs")
    op.drop_index(op.f("ix_integration_configs_amo_id"), table_name="integration_configs")
    op.drop_index("ix_integration_configs_amo_key", table_name="integration_configs")
    op.drop_table("integration_configs")
