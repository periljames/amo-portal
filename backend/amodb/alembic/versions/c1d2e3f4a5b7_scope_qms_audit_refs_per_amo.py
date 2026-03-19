"""scope qms audit refs per amo

Revision ID: c1d2e3f4a5b7
Revises: a7b8c9d0e1f2
Create Date: 2026-03-19 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b7"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _constraint_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {item["name"] for item in sa.inspect(bind).get_unique_constraints(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {item["name"] for item in sa.inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE qms_audits AS audit
            SET amo_id = users.amo_id
            FROM users
            WHERE audit.amo_id IS NULL
              AND audit.created_by_user_id = users.id
            """
        )
    )

    constraints = _constraint_names("qms_audits")
    if "uq_qms_audit_ref" in constraints:
        op.drop_constraint("uq_qms_audit_ref", "qms_audits", type_="unique")
    if "uq_qms_audit_ref_scope" in constraints:
        op.drop_constraint("uq_qms_audit_ref_scope", "qms_audits", type_="unique")

    constraints = _constraint_names("qms_audits")
    if "uq_qms_audit_ref_per_amo" not in constraints:
        op.create_unique_constraint("uq_qms_audit_ref_per_amo", "qms_audits", ["amo_id", "domain", "audit_ref"])
    if "uq_qms_audit_ref_scope_per_amo" not in constraints:
        op.create_unique_constraint(
            "uq_qms_audit_ref_scope_per_amo",
            "qms_audits",
            ["amo_id", "domain", "reference_family", "unit_code", "ref_year", "ref_sequence"],
        )

    indexes = _index_names("qms_audits")
    if "ix_qms_audits_amo_domain_created" not in indexes:
        op.create_index("ix_qms_audits_amo_domain_created", "qms_audits", ["amo_id", "domain", "created_at"], unique=False)


def downgrade() -> None:
    indexes = _index_names("qms_audits")
    if "ix_qms_audits_amo_domain_created" in indexes:
        op.drop_index("ix_qms_audits_amo_domain_created", table_name="qms_audits")

    constraints = _constraint_names("qms_audits")
    if "uq_qms_audit_ref_scope_per_amo" in constraints:
        op.drop_constraint("uq_qms_audit_ref_scope_per_amo", "qms_audits", type_="unique")
    if "uq_qms_audit_ref_per_amo" in constraints:
        op.drop_constraint("uq_qms_audit_ref_per_amo", "qms_audits", type_="unique")

    op.create_unique_constraint("uq_qms_audit_ref", "qms_audits", ["domain", "audit_ref"])
    op.create_unique_constraint(
        "uq_qms_audit_ref_scope",
        "qms_audits",
        ["domain", "reference_family", "unit_code", "ref_year", "ref_sequence"],
    )
