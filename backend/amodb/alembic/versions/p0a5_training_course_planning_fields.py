"""P0 training course planning fields with parallel-branch safety.

Revision ID: p0a5_train_plan
Revises: p0a4_training_gate_fields
Create Date: 2026-04-09 00:00:00.000000

The Training schema may be created on another branch after this revision. This
migration applies available changes idempotently; the SaaS convergence
migration guarantees the same fields and checks once the full graph exists.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p0a5_train_plan"
down_revision = "p0a4_training_gate_fields"
branch_labels = None
depends_on = None

TABLE_NAME = "training_courses"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists() -> bool:
    return _inspector().has_table(TABLE_NAME)


def _columns() -> set[str]:
    if not _table_exists():
        return set()
    return {str(column["name"]) for column in _inspector().get_columns(TABLE_NAME)}


def _check_names() -> set[str]:
    if not _table_exists():
        return set()
    return {
        str(item.get("name"))
        for item in _inspector().get_check_constraints(TABLE_NAME)
        if item.get("name")
    }


def _add_column_if_missing(column: sa.Column) -> None:
    if _table_exists() and column.name not in _columns():
        op.add_column(TABLE_NAME, column)


def upgrade() -> None:
    if not _table_exists():
        return

    _add_column_if_missing(sa.Column("nominal_hours", sa.Integer(), nullable=True))
    _add_column_if_missing(
        sa.Column("planning_lead_days", sa.Integer(), nullable=True, server_default=sa.text("45"))
    )
    _add_column_if_missing(sa.Column("candidate_requirement_text", sa.Text(), nullable=True))

    checks = _check_names()
    if "nominal_hours" in _columns() and "ck_training_course_nominal_hours_nonneg" not in checks:
        op.create_check_constraint(
            "ck_training_course_nominal_hours_nonneg",
            TABLE_NAME,
            "nominal_hours IS NULL OR nominal_hours >= 0",
        )
    checks = _check_names()
    if "planning_lead_days" in _columns() and "ck_training_course_planning_lead_nonneg" not in checks:
        op.create_check_constraint(
            "ck_training_course_planning_lead_nonneg",
            TABLE_NAME,
            "planning_lead_days IS NULL OR planning_lead_days >= 0",
        )


def downgrade() -> None:
    if not _table_exists():
        return
    for constraint_name in (
        "ck_training_course_planning_lead_nonneg",
        "ck_training_course_nominal_hours_nonneg",
    ):
        if constraint_name in _check_names():
            op.drop_constraint(constraint_name, TABLE_NAME, type_="check")
    for column_name in ("candidate_requirement_text", "planning_lead_days", "nominal_hours"):
        if column_name in _columns():
            op.drop_column(TABLE_NAME, column_name)
