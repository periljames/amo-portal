"""Add structured compliance assessment fields to audit checklist execution.

Revision ID: quality_261001_compliance_intel
Revises: quality_260930_auditor_foundation
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa


revision = "quality_261001_compliance_intel"
down_revision = "quality_260930_auditor_foundation"
branch_labels = None
depends_on = None

TABLE = "quality_audit_checklist_execution_governance"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return set()
    return {column["name"] for column in inspector.get_columns(TABLE)}


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return

    additions = (
        ("assessment_applicability", sa.String(length=24), "UNVERIFIED"),
        ("documentary_status", sa.String(length=32), "UNVERIFIED"),
        ("implementation_status", sa.String(length=32), "UNVERIFIED"),
        ("field_verification_status", sa.String(length=32), "UNVERIFIED"),
    )
    for name, column_type, default in additions:
        if name not in columns:
            op.add_column(
                TABLE,
                sa.Column(name, column_type, nullable=False, server_default=default),
            )

    json_columns = (
        "evidence_ids",
        "document_revision_ids",
        "regulation_refs",
        "procedure_refs",
        "conflicts",
        "missing_evidence",
        "fieldwork_requirements",
    )
    columns = _columns()
    for name in json_columns:
        if name not in columns:
            op.add_column(
                TABLE,
                sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            )

    columns = _columns()
    if "applicability_reason" not in columns:
        op.add_column(TABLE, sa.Column("applicability_reason", sa.Text(), nullable=True))
    if "applicability_basis" not in columns:
        op.add_column(
            TABLE,
            sa.Column("applicability_basis", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
    if "ai_analysis" not in columns:
        op.add_column(TABLE, sa.Column("ai_analysis", sa.JSON(), nullable=True))
    if "human_decision" not in columns:
        op.add_column(TABLE, sa.Column("human_decision", sa.String(length=24), nullable=True))
    if "human_override_reason" not in columns:
        op.add_column(TABLE, sa.Column("human_override_reason", sa.Text(), nullable=True))

    if _is_postgresql():
        op.create_check_constraint(
            "ck_quality_checklist_execution_assessment_applicability",
            TABLE,
            "assessment_applicability IN ('APPLICABLE','NOT_APPLICABLE','UNVERIFIED')",
        )
        op.create_check_constraint(
            "ck_quality_checklist_execution_documentary_status",
            TABLE,
            "documentary_status IN ('DOCUMENTED','NOT_DOCUMENTED','PARTIALLY_DOCUMENTED','CONFLICT','NOT_EVIDENCED','UNVERIFIED')",
        )
        op.create_check_constraint(
            "ck_quality_checklist_execution_implementation_status",
            TABLE,
            "implementation_status IN ('OBJECTIVE_EVIDENCE_AVAILABLE','VERIFIED','NOT_VERIFIED','NOT_EVIDENCED','UNVERIFIED')",
        )
        op.create_check_constraint(
            "ck_quality_checklist_execution_field_status",
            TABLE,
            "field_verification_status IN ('FIELD_VERIFICATION_REQUIRED','VERIFIED','NOT_VERIFIED','NOT_APPLICABLE','UNVERIFIED')",
        )


def downgrade() -> None:
    columns = _columns()
    if not columns:
        return
    if _is_postgresql():
        for name in (
            "ck_quality_checklist_execution_field_status",
            "ck_quality_checklist_execution_implementation_status",
            "ck_quality_checklist_execution_documentary_status",
            "ck_quality_checklist_execution_assessment_applicability",
        ):
            op.drop_constraint(name, TABLE, type_="check")

    for name in (
        "human_override_reason",
        "human_decision",
        "ai_analysis",
        "applicability_basis",
        "applicability_reason",
        "fieldwork_requirements",
        "missing_evidence",
        "conflicts",
        "procedure_refs",
        "regulation_refs",
        "document_revision_ids",
        "evidence_ids",
        "field_verification_status",
        "implementation_status",
        "documentary_status",
        "assessment_applicability",
    ):
        if name in _columns():
            op.drop_column(TABLE, name)
