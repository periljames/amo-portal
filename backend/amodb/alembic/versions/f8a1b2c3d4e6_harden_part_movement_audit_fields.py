"""harden part movement audit fields

Revision ID: f8a1b2c3d4e6
Revises: f7c8d9e0f1a2
Create Date: 2025-01-12 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8a1b2c3d4e6"
down_revision: Union[str, Sequence[str], None] = "f7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PART_MOVEMENT_TYPES = (
    "RECEIVE",
    "ISSUE",
    "TRANSFER",
    "RETURN",
    "ADJUST",
    "SCRAP",
    "VENDOR_RETURN",
    "INSTALL",
    "REMOVE",
    "SWAP",
    "INSPECT",
)


def upgrade() -> None:
    op.add_column(
        "part_movement_ledger",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_part_movement_ledger_created_by_user_id_users"),
        "part_movement_ledger",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE part_movement_ledger
        SET created_by_user_id = (
            SELECT users.id
            FROM users
            WHERE users.amo_id = part_movement_ledger.amo_id
            ORDER BY users.created_at
            LIMIT 1
        )
        WHERE created_by_user_id IS NULL
        """
    )
    op.alter_column("part_movement_ledger", "created_by_user_id", nullable=False)

    op.execute("ALTER TABLE part_movement_ledger DROP CONSTRAINT IF EXISTS part_movement_type_enum")
    op.create_check_constraint(
        "part_movement_type_enum",
        "part_movement_ledger",
        f"event_type IN {PART_MOVEMENT_TYPES}",
    )
    op.create_check_constraint(
        "ck_part_movement_reason_code_required",
        "part_movement_ledger",
        "(event_type NOT IN ('ADJUST', 'SCRAP', 'REMOVE', 'SWAP', 'VENDOR_RETURN')) "
        "OR (reason_code IS NOT NULL AND length(trim(reason_code)) > 0)",
    )
    op.create_index("ix_part_movement_amo_event_date", "part_movement_ledger", ["amo_id", "event_date"], unique=False)
    op.create_index("ix_part_movement_amo_created", "part_movement_ledger", ["amo_id", "created_at"], unique=False)

    op.add_column(
        "removal_events",
        sa.Column(
            "event_type",
            sa.Enum(*PART_MOVEMENT_TYPES, name="removal_event_type_enum", native_enum=False),
            nullable=False,
            server_default="REMOVE",
        ),
    )
    op.add_column(
        "removal_events",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_removal_events_created_by_user_id_users"),
        "removal_events",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE removal_events
        SET created_by_user_id = (
            SELECT users.id
            FROM users
            WHERE users.amo_id = removal_events.amo_id
            ORDER BY users.created_at
            LIMIT 1
        )
        WHERE created_by_user_id IS NULL
        """
    )
    op.alter_column("removal_events", "created_by_user_id", nullable=False)
    op.alter_column("removal_events", "event_type", server_default=None)
    op.create_check_constraint(
        "removal_event_type_enum",
        "removal_events",
        "event_type IN ('REMOVE', 'SWAP')",
    )
    op.create_check_constraint(
        "ck_removal_tracking_required",
        "removal_events",
        "(event_type NOT IN ('REMOVE', 'SWAP')) OR removal_tracking_id IS NOT NULL",
    )
    op.create_index("ix_removal_events_amo_removed", "removal_events", ["amo_id", "removed_at"], unique=False)
    op.create_index("ix_removal_events_amo_created", "removal_events", ["amo_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_removal_events_amo_created", table_name="removal_events")
    op.drop_index("ix_removal_events_amo_removed", table_name="removal_events")
    op.drop_constraint("ck_removal_tracking_required", "removal_events", type_="check")
    op.drop_constraint("removal_event_type_enum", "removal_events", type_="check")
    op.drop_constraint(op.f("fk_removal_events_created_by_user_id_users"), "removal_events", type_="foreignkey")
    op.drop_column("removal_events", "created_by_user_id")
    op.drop_column("removal_events", "event_type")

    op.drop_index("ix_part_movement_amo_created", table_name="part_movement_ledger")
    op.drop_index("ix_part_movement_amo_event_date", table_name="part_movement_ledger")
    op.drop_constraint("ck_part_movement_reason_code_required", "part_movement_ledger", type_="check")
    op.drop_constraint("part_movement_type_enum", "part_movement_ledger", type_="check")
    op.create_check_constraint(
        "part_movement_type_enum",
        "part_movement_ledger",
        "event_type IN ('INSTALL', 'REMOVE', 'SWAP', 'INSPECT')",
    )
    op.drop_constraint(
        op.f("fk_part_movement_ledger_created_by_user_id_users"),
        "part_movement_ledger",
        type_="foreignkey",
    )
    op.drop_column("part_movement_ledger", "created_by_user_id")
