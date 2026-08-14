"""Course delivery controls and licence-expiry provenance.

Revision ID: training_20260814_plan_controls
Revises: training_20260814_licence_text
Create Date: 2026-08-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_20260814_plan_controls"
down_revision = "training_20260814_licence_text"
branch_labels = None
depends_on = None


COURSE_COLUMNS = (
    sa.Column("default_facility", sa.String(length=255), nullable=True),
    sa.Column("default_instructor_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    sa.Column("cost_currency", sa.String(length=3), nullable=False, server_default="USD"),
    sa.Column("estimated_unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("default_capacity", sa.Integer(), nullable=True),
    sa.Column("group_code", sa.String(length=64), nullable=True),
    sa.Column("licence_authority", sa.String(length=64), nullable=True),
)

LICENCE_COLUMNS = (
    sa.Column("expiry_source_record_id", sa.String(length=36), nullable=True),
    sa.Column("expiry_source_course_id", sa.String(length=36), nullable=True),
    sa.Column("expiry_synced_at", sa.DateTime(timezone=True), nullable=True),
)

PLAN_ITEM_COLUMNS = (
    sa.Column("instructor_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {str(index["name"]) for index in inspector.get_indexes(table_name)}


def _foreign_keys(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {str(constraint["name"]) for constraint in inspector.get_foreign_keys(table_name) if constraint.get("name")}


def upgrade() -> None:
    course_columns = _columns("training_courses")
    for column in COURSE_COLUMNS:
        if column.name not in course_columns:
            op.add_column("training_courses", column)
    if "ix_training_courses_amo_group" not in _indexes("training_courses"):
        op.create_index("ix_training_courses_amo_group", "training_courses", ["amo_id", "group_code"])

    licence_columns = _columns("personnel_licences")
    for column in LICENCE_COLUMNS:
        if column.name not in licence_columns:
            op.add_column("personnel_licences", column)
    foreign_keys = _foreign_keys("personnel_licences")
    if "fk_personnel_licences_expiry_record" not in foreign_keys:
        op.create_foreign_key(
            "fk_personnel_licences_expiry_record",
            "personnel_licences",
            "training_records",
            ["expiry_source_record_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "fk_personnel_licences_expiry_course" not in foreign_keys:
        op.create_foreign_key(
            "fk_personnel_licences_expiry_course",
            "personnel_licences",
            "training_courses",
            ["expiry_source_course_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_personnel_licences_expiry_source" not in _indexes("personnel_licences"):
        op.create_index(
            "ix_personnel_licences_expiry_source",
            "personnel_licences",
            ["amo_id", "expiry_source_record_id"],
        )

    plan_item_columns = _columns("training_plan_items")
    for column in PLAN_ITEM_COLUMNS:
        if column.name not in plan_item_columns:
            op.add_column("training_plan_items", column)


def downgrade() -> None:
    plan_item_columns = _columns("training_plan_items")
    for column in reversed(PLAN_ITEM_COLUMNS):
        if column.name in plan_item_columns:
            op.drop_column("training_plan_items", column.name)
    if "ix_personnel_licences_expiry_source" in _indexes("personnel_licences"):
        op.drop_index("ix_personnel_licences_expiry_source", table_name="personnel_licences")
    foreign_keys = _foreign_keys("personnel_licences")
    if "fk_personnel_licences_expiry_course" in foreign_keys:
        op.drop_constraint("fk_personnel_licences_expiry_course", "personnel_licences", type_="foreignkey")
    if "fk_personnel_licences_expiry_record" in foreign_keys:
        op.drop_constraint("fk_personnel_licences_expiry_record", "personnel_licences", type_="foreignkey")
    licence_columns = _columns("personnel_licences")
    for column in reversed(LICENCE_COLUMNS):
        if column.name in licence_columns:
            op.drop_column("personnel_licences", column.name)

    if "ix_training_courses_amo_group" in _indexes("training_courses"):
        op.drop_index("ix_training_courses_amo_group", table_name="training_courses")
    course_columns = _columns("training_courses")
    for column in reversed(COURSE_COLUMNS):
        if column.name in course_columns:
            op.drop_column("training_courses", column.name)
