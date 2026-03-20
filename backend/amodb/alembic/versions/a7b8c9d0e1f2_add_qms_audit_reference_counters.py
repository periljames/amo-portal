"""add qms audit reference counters

Revision ID: a7b8c9d0e1f2
Revises: z9y8x7w6v5u4
Create Date: 2026-03-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "z9y8x7w6v5u4"
branch_labels = None
depends_on = None


_AUDIT_COLUMN_DEFAULTS: dict[str, tuple[sa.types.TypeEngine, str]] = {
    "reference_family": (sa.String(length=16), "QAR"),
    "unit_code": (sa.String(length=16), "MO"),
    "ref_year": (sa.Integer(), "26"),
    "ref_sequence": (sa.Integer(), "1"),
}


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _constraint_names(table_name: str) -> set[str]:
    return {item["name"] for item in _inspector().get_unique_constraints(table_name) if item.get("name")}


def _index_names(table_name: str) -> set[str]:
    return {item["name"] for item in _inspector().get_indexes(table_name) if item.get("name")}


def upgrade() -> None:
    if not _table_exists("qms_audit_reference_counters"):
        op.create_table(
            "qms_audit_reference_counters",
            sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("reference_family", sa.String(length=16), nullable=False),
            sa.Column("unit_code", sa.String(length=16), nullable=False),
            sa.Column("ref_year", sa.Integer(), nullable=False),
            sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "amo_id",
                "reference_family",
                "unit_code",
                "ref_year",
                name="uq_qms_audit_ref_counter_scope",
            ),
        )

    counter_indexes = _index_names("qms_audit_reference_counters")
    if "ix_qms_audit_ref_counter_scope" not in counter_indexes:
        op.create_index(
            "ix_qms_audit_ref_counter_scope",
            "qms_audit_reference_counters",
            ["amo_id", "reference_family", "unit_code", "ref_year"],
            unique=False,
        )

    audit_columns = _column_names("qms_audits")
    for column_name, (column_type, default) in _AUDIT_COLUMN_DEFAULTS.items():
        if column_name not in audit_columns:
            op.add_column(
                "qms_audits",
                sa.Column(column_name, column_type, nullable=False, server_default=default),
            )

    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 COALESCE(EXTRACT(YEAR FROM created_at)::int % 100, 26) AS next_ref_year,
                 ROW_NUMBER() OVER (
                   PARTITION BY domain, COALESCE(EXTRACT(YEAR FROM created_at)::int % 100, 26)
                   ORDER BY created_at, id
                 ) AS next_ref_sequence
          FROM qms_audits
        )
        UPDATE qms_audits AS audit
        SET reference_family = COALESCE(audit.reference_family, 'QAR'),
            unit_code = COALESCE(audit.unit_code, 'MO'),
            ref_year = COALESCE(audit.ref_year, ranked.next_ref_year),
            ref_sequence = COALESCE(audit.ref_sequence, ranked.next_ref_sequence)
        FROM ranked
        WHERE audit.id = ranked.id
        """
    )

    constraints = _constraint_names("qms_audits")
    if "uq_qms_audit_ref_scope" not in constraints:
        op.create_unique_constraint(
            "uq_qms_audit_ref_scope",
            "qms_audits",
            ["domain", "reference_family", "unit_code", "ref_year", "ref_sequence"],
        )

    audit_columns = _column_names("qms_audits")
    for column_name in _AUDIT_COLUMN_DEFAULTS:
        if column_name in audit_columns:
            op.alter_column("qms_audits", column_name, server_default=None)


def downgrade() -> None:
    constraints = _constraint_names("qms_audits")
    if "uq_qms_audit_ref_scope" in constraints:
        op.drop_constraint("uq_qms_audit_ref_scope", "qms_audits", type_="unique")

    audit_columns = _column_names("qms_audits")
    for column_name in ["ref_sequence", "ref_year", "unit_code", "reference_family"]:
        if column_name in audit_columns:
            op.drop_column("qms_audits", column_name)

    if _table_exists("qms_audit_reference_counters"):
        indexes = _index_names("qms_audit_reference_counters")
        if "ix_qms_audit_ref_counter_scope" in indexes:
            op.drop_index("ix_qms_audit_ref_counter_scope", table_name="qms_audit_reference_counters")
        op.drop_table("qms_audit_reference_counters")
