"""harden part movement audit fields

Revision ID: f8a1b2c3d4e6
Revises: f7c8d9e0f1a2
Create Date: 2025-01-12 14:30:00.000000

"""
from typing import Sequence, Union
from datetime import datetime, timezone
from uuid import uuid4

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
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    users_table = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("amo_id", sa.String),
        sa.column("staff_code", sa.String),
        sa.column("email", sa.String),
        sa.column("first_name", sa.String),
        sa.column("last_name", sa.String),
        sa.column("full_name", sa.String),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_superuser", sa.Boolean),
        sa.column("is_amo_admin", sa.Boolean),
        sa.column("is_system_account", sa.Boolean),
        sa.column("hashed_password", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    part_movement_table = sa.table(
        "part_movement_ledger",
        sa.column("amo_id", sa.String),
        sa.column("created_by_user_id", sa.String),
    )
    removal_table = sa.table(
        "removal_events",
        sa.column("amo_id", sa.String),
        sa.column("created_by_user_id", sa.String),
    )

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

    amo_ids = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT DISTINCT amo_id FROM part_movement_ledger WHERE created_by_user_id IS NULL"
            )
        )
    } | {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT DISTINCT amo_id FROM removal_events WHERE created_by_user_id IS NULL"
            )
        )
    }

    for amo_id in amo_ids:
        if amo_id is None:
            continue
        user_id = conn.execute(
            sa.select(users_table.c.id).where(users_table.c.amo_id == amo_id).limit(1)
        ).scalar()
        if user_id is None:
            user_id = f"SYS-{uuid4()}"
            staff_code = f"SYSTEM-{amo_id[:6]}".upper()
            conn.execute(
                users_table.insert().values(
                    id=user_id,
                    amo_id=amo_id,
                    staff_code=staff_code,
                    email=f"system+{amo_id}@amo.local",
                    first_name="System",
                    last_name="User",
                    full_name="System User",
                    role="TECHNICIAN",
                    is_active=True,
                    is_superuser=False,
                    is_amo_admin=False,
                    is_system_account=True,
                    hashed_password="SYSTEM",
                    created_at=now,
                    updated_at=now,
                )
            )
        conn.execute(
            part_movement_table.update()
            .where(
                sa.and_(
                    part_movement_table.c.amo_id == amo_id,
                    part_movement_table.c.created_by_user_id.is_(None),
                )
            )
            .values(created_by_user_id=user_id)
        )
        conn.execute(
            removal_table.update()
            .where(
                sa.and_(
                    removal_table.c.amo_id == amo_id,
                    removal_table.c.created_by_user_id.is_(None),
                )
            )
            .values(created_by_user_id=user_id)
        )

    remaining_part_movement = conn.execute(
        sa.select(sa.func.count())
        .select_from(part_movement_table)
        .where(part_movement_table.c.created_by_user_id.is_(None))
    ).scalar()
    remaining_removal = conn.execute(
        sa.select(sa.func.count())
        .select_from(removal_table)
        .where(removal_table.c.created_by_user_id.is_(None))
    ).scalar()
    if remaining_part_movement or remaining_removal:
        raise RuntimeError("created_by_user_id backfill failed; NULLs remain.")

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
        sa.Column("event_type", sa.String(length=16), nullable=False, server_default="REMOVE"),
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
    op.alter_column("removal_events", "created_by_user_id", nullable=False)
    op.alter_column("removal_events", "event_type", server_default=None)
    op.create_check_constraint(
        "ck_removal_event_type_allowed",
        "removal_events",
        "event_type IN ('REMOVE', 'SWAP')",
    )
    op.create_index("ix_removal_events_amo_removed", "removal_events", ["amo_id", "removed_at"], unique=False)
    op.create_index("ix_removal_events_amo_created", "removal_events", ["amo_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_removal_events_amo_created", table_name="removal_events")
    op.drop_index("ix_removal_events_amo_removed", table_name="removal_events")
    op.drop_constraint("ck_removal_event_type_allowed", "removal_events", type_="check")
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
