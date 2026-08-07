"""add immutable manual daily utilisation ledger

Revision ID: aircraft_arch_20260805_daily_utilisation
Revises: aircraft_arch_20260805_u4_import_lifecycle
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aircraft_arch_20260805_daily_utilisation"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260805_u4_import_lifecycle"
branch_labels = None
depends_on = None

UUID = sa.String(length=36)
NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "aircraft_daily_utilisation_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_date", sa.Date(), nullable=False),
        sa.Column("techlog_no", sa.String(64), nullable=False),
        sa.Column("station", sa.String(16), nullable=True),
        sa.Column("flight_hours", sa.Numeric(12, 2), nullable=False),
        sa.Column("cycles", sa.Integer(), nullable=False),
        sa.Column("nil_operation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="MANUAL"),
        sa.Column("source_reference", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_entry_id", UUID, sa.ForeignKey("aircraft_daily_utilisation_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("posted_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_daily_util_idempotency"),
        sa.UniqueConstraint("amo_id", "aircraft_serial_number", "operation_date", "revision_no", name="uq_daily_util_aircraft_date_revision"),
        sa.CheckConstraint("flight_hours >= 0", name="ck_daily_util_hours_nonneg"),
        sa.CheckConstraint("cycles >= 0", name="ck_daily_util_cycles_nonneg"),
        sa.CheckConstraint("status IN ('DRAFT','POSTED','SUPERSEDED','REJECTED')", name="ck_daily_util_status"),
        sa.CheckConstraint("source_type IN ('MANUAL','CSV','EFB','INTEGRATION')", name="ck_daily_util_source_type"),
    )
    op.create_index("ix_daily_util_aircraft_date", "aircraft_daily_utilisation_entries", ["amo_id", "aircraft_serial_number", "operation_date"])
    op.create_index("ix_daily_util_status", "aircraft_daily_utilisation_entries", ["amo_id", "status", "operation_date"])

    op.create_table(
        "aircraft_daily_utilisation_exposures",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("entry_id", UUID, sa.ForeignKey("aircraft_daily_utilisation_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("component_id", sa.Integer(), sa.ForeignKey("aircraft_components.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("component_position", sa.String(50), nullable=False),
        sa.Column("component_description", sa.String(255), nullable=True),
        sa.Column("derivation", sa.String(24), nullable=False),
        sa.Column("hours_delta", sa.Numeric(12, 2), nullable=False),
        sa.Column("cycles_delta", sa.Integer(), nullable=False),
        sa.Column("before_hours", sa.Numeric(14, 2), nullable=True),
        sa.Column("before_cycles", sa.Integer(), nullable=True),
        sa.Column("after_hours", sa.Numeric(14, 2), nullable=True),
        sa.Column("after_cycles", sa.Integer(), nullable=True),
        sa.Column("baseline_missing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("entry_id", "target_type", "component_id", name="uq_daily_util_exposure_target"),
        sa.CheckConstraint("target_type IN ('AIRFRAME','ENGINE','PROPELLER','APU','COMPONENT')", name="ck_daily_util_exposure_target"),
        sa.CheckConstraint("hours_delta >= 0", name="ck_daily_util_exposure_hours"),
        sa.CheckConstraint("cycles_delta >= 0", name="ck_daily_util_exposure_cycles"),
    )
    op.create_index("ix_daily_util_exposure_entry", "aircraft_daily_utilisation_exposures", ["entry_id", "target_type"])


def downgrade() -> None:
    op.drop_table("aircraft_daily_utilisation_exposures")
    op.drop_table("aircraft_daily_utilisation_entries")
