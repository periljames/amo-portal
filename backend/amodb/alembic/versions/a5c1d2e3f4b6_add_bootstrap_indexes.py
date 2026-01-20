"""Add bootstrap workflow indexes.

Revision ID: a5c1d2e3f4b6
Revises: f4c7f0c1d2ab
Create Date: 2025-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "a5c1d2e3f4b6"
down_revision = "f4c7f0c1d2ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_work_orders_amo_aircraft_created",
        "work_orders",
        ["amo_id", "aircraft_serial_number", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_task_cards_amo_workorder_status",
        "task_cards",
        ["amo_id", "work_order_id", "status"],
    )
    op.create_index(
        "ix_audit_events_amo_time_desc",
        "audit_events",
        ["amo_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_config_events_amo_aircraft_date_desc",
        "aircraft_configuration_events",
        ["amo_id", "aircraft_serial_number", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_part_movement_amo_aircraft_date",
        "part_movement_ledger",
        ["amo_id", "aircraft_serial_number", sa.text("event_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_part_movement_amo_aircraft_date", table_name="part_movement_ledger")
    op.drop_index(
        "ix_config_events_amo_aircraft_date_desc",
        table_name="aircraft_configuration_events",
    )
    op.drop_index("ix_audit_events_amo_time_desc", table_name="audit_events")
    op.drop_index("ix_task_cards_amo_workorder_status", table_name="task_cards")
    op.drop_index("ix_work_orders_amo_aircraft_created", table_name="work_orders")
