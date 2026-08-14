"""Participant-level expiry provenance for monthly training plans.

Revision ID: training_20260813_expiry_plan
Revises: training_20260813_operating_system
Create Date: 2026-08-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_20260813_expiry_plan"
down_revision = "training_20260813_operating_system"
branch_labels = None
depends_on = None


FIELDS = [
    ("person_name_snapshot", sa.String(length=255), False, "Unknown personnel"),
    ("staff_code_snapshot", sa.String(length=64), True, None),
    ("last_completion_date", sa.Date(), True, None),
    ("expiry_date", sa.Date(), True, None),
    ("planned_due_date", sa.Date(), True, None),
    ("obligation_status", sa.String(length=32), False, "PLANNED"),
    ("source_type", sa.String(length=32), False, "REQUIREMENT"),
    ("source_record_id", sa.String(length=36), True, None),
    ("source_reference", sa.String(length=255), True, None),
]


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("training_plan_participants")}


def upgrade() -> None:
    existing = _columns()
    for name, column_type, nullable, default in FIELDS:
        if name in existing:
            continue
        op.add_column(
            "training_plan_participants",
            sa.Column(name, column_type, nullable=nullable, server_default=default),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("training_plan_participants")}
    if "ix_training_plan_participant_due" not in indexes:
        op.create_index(
            "ix_training_plan_participant_due",
            "training_plan_participants",
            ["amo_id", "planned_due_date"],
        )


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("training_plan_participants")}
    if "ix_training_plan_participant_due" in indexes:
        op.drop_index("ix_training_plan_participant_due", table_name="training_plan_participants")
    existing = _columns()
    for name, _column_type, _nullable, _default in reversed(FIELDS):
        if name in existing:
            op.drop_column("training_plan_participants", name)
