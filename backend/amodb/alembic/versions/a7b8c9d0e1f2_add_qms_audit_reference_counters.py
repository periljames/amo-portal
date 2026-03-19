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


def upgrade() -> None:
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
        sa.UniqueConstraint("amo_id", "reference_family", "unit_code", "ref_year", name="uq_qms_audit_ref_counter_scope"),
    )
    op.create_index(
        "ix_qms_audit_ref_counter_scope",
        "qms_audit_reference_counters",
        ["amo_id", "reference_family", "unit_code", "ref_year"],
        unique=False,
    )

    op.add_column("qms_audits", sa.Column("reference_family", sa.String(length=16), nullable=False, server_default="QAR"))
    op.add_column("qms_audits", sa.Column("unit_code", sa.String(length=16), nullable=False, server_default="MO"))
    op.add_column("qms_audits", sa.Column("ref_year", sa.Integer(), nullable=False, server_default="26"))
    op.add_column("qms_audits", sa.Column("ref_sequence", sa.Integer(), nullable=False, server_default="1"))

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
        SET reference_family = 'QAR',
            unit_code = 'MO',
            ref_year = ranked.next_ref_year,
            ref_sequence = ranked.next_ref_sequence
        FROM ranked
        WHERE audit.id = ranked.id
        """
    )

    op.create_unique_constraint("uq_qms_audit_ref_scope", "qms_audits", ["domain", "reference_family", "unit_code", "ref_year", "ref_sequence"])

    op.alter_column("qms_audits", "reference_family", server_default=None)
    op.alter_column("qms_audits", "unit_code", server_default=None)
    op.alter_column("qms_audits", "ref_year", server_default=None)
    op.alter_column("qms_audits", "ref_sequence", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_qms_audit_ref_scope", "qms_audits", type_="unique")
    op.drop_column("qms_audits", "ref_sequence")
    op.drop_column("qms_audits", "ref_year")
    op.drop_column("qms_audits", "unit_code")
    op.drop_column("qms_audits", "reference_family")

    op.drop_index("ix_qms_audit_ref_counter_scope", table_name="qms_audit_reference_counters")
    op.drop_table("qms_audit_reference_counters")
