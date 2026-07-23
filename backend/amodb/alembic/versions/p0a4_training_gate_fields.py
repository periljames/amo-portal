"""P0 training-gate fields with parallel-branch safety.

Revision ID: p0a4_training_gate_fields
Revises: p0a3_compliance_event_ledger
Create Date: 2026-03-09 00:00:00.000000

Document-control and Training tables are created on separate Alembic branches,
so a clean installation may reach this historical revision before either target
exists. Missing work is repeated by the SaaS convergence migration.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p0a4_training_gate_fields"
down_revision = "p0a3_compliance_event_ledger"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _index_names(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {
        str(index.get("name"))
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def upgrade() -> None:
    _add_column_if_missing(
        "doc_control_revision_packages",
        sa.Column("requires_training", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _add_column_if_missing(
        "doc_control_revision_packages",
        sa.Column("training_gate_policy", sa.String(length=32), nullable=False, server_default="NONE"),
    )

    _add_column_if_missing("training_requirements", sa.Column("source_type", sa.String(length=32), nullable=True))
    _add_column_if_missing("training_requirements", sa.Column("source_id", sa.String(length=64), nullable=True))
    _add_column_if_missing(
        "training_requirements",
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _add_column_if_missing("training_requirements", sa.Column("required_by_date", sa.Date(), nullable=True))

    required = {"amo_id", "source_type", "source_id"}
    if required.issubset(_columns("training_requirements")):
        index_name = "ix_training_requirements_amo_source"
        if index_name not in _index_names("training_requirements"):
            op.create_index(index_name, "training_requirements", ["amo_id", "source_type", "source_id"])


def downgrade() -> None:
    index_name = "ix_training_requirements_amo_source"
    if index_name in _index_names("training_requirements"):
        op.drop_index(index_name, table_name="training_requirements")

    for table_name, columns in (
        ("training_requirements", ("required_by_date", "blocking", "source_id", "source_type")),
        ("doc_control_revision_packages", ("training_gate_policy", "requires_training")),
    ):
        for column_name in columns:
            if column_name in _columns(table_name):
                op.drop_column(table_name, column_name)
