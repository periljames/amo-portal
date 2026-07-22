"""Finalize tenant-scoped bootstrap indexes after all Alembic branches converge.

Revision ID: saas_20260722_finalize_idx
Revises: saas_20260722_control_plane
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = "saas_20260722_finalize_idx"
down_revision = "saas_20260722_control_plane"
branch_labels = None
depends_on = None


INDEXES: tuple[tuple[str, str, tuple[object, ...], tuple[str, ...]], ...] = (
    (
        "ix_work_orders_amo_aircraft_created",
        "work_orders",
        ("amo_id", "aircraft_serial_number", sa.text("created_at DESC")),
        ("amo_id", "aircraft_serial_number", "created_at"),
    ),
    (
        "ix_task_cards_amo_workorder_status",
        "task_cards",
        ("amo_id", "work_order_id", "status"),
        ("amo_id", "work_order_id", "status"),
    ),
    (
        "ix_audit_events_amo_time_desc",
        "audit_events",
        ("amo_id", sa.text("occurred_at DESC")),
        ("amo_id", "occurred_at"),
    ),
    (
        "ix_config_events_amo_aircraft_date_desc",
        "aircraft_configuration_events",
        ("amo_id", "aircraft_serial_number", sa.text("occurred_at DESC")),
        ("amo_id", "aircraft_serial_number", "occurred_at"),
    ),
    (
        "ix_part_movement_amo_aircraft_date",
        "part_movement_ledger",
        ("amo_id", "aircraft_serial_number", sa.text("event_date DESC")),
        ("amo_id", "aircraft_serial_number", "event_date"),
    ),
)


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    if not inspector.has_table(table_name):
        return set()
    return {str(index.get("name")) for index in inspector.get_indexes(table_name) if index.get("name")}


def _has_columns(inspector: sa.Inspector, table_name: str, columns: Iterable[str]) -> bool:
    if not inspector.has_table(table_name):
        return False
    available = {str(column["name"]) for column in inspector.get_columns(table_name)}
    return set(columns).issubset(available)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for name, table_name, expressions, required_columns in INDEXES:
        if not _has_columns(inspector, table_name, required_columns):
            continue
        if name in _index_names(inspector, table_name):
            continue
        op.create_index(name, table_name, list(expressions))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for name, table_name, _expressions, _required_columns in reversed(INDEXES):
        if name in _index_names(inspector, table_name):
            op.drop_index(name, table_name=table_name)
