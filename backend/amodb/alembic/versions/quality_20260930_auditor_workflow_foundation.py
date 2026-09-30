"""Separate audit preparation request stage from mutable execution state.

Revision ID: quality_260930_auditor_foundation
Revises: workforce_260929_leave_gov
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_260930_auditor_foundation"
down_revision = "workforce_260929_leave_gov"
branch_labels = None
depends_on = None

DOC_META = "quality_audit_document_request_metadata"


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns(DOC_META)
    if columns and "requirement_stage" not in columns:
        op.add_column(
            DOC_META,
            sa.Column(
                "requirement_stage",
                sa.String(length=32),
                nullable=False,
                server_default="REQUIRED_BEFORE_ISSUE",
            ),
        )
        op.create_check_constraint(
            "ck_quality_audit_doc_meta_requirement_stage",
            DOC_META,
            "requirement_stage IN ('REQUIRED_BEFORE_ISSUE','REQUIRED_BEFORE_FIELDWORK','REQUIRED_DURING_FIELDWORK','REQUESTED_NOT_BLOCKING')",
        )


def downgrade() -> None:
    columns = _columns(DOC_META)
    if columns and "requirement_stage" in columns:
        op.drop_constraint(
            "ck_quality_audit_doc_meta_requirement_stage",
            DOC_META,
            type_="check",
        )
        op.drop_column(DOC_META, "requirement_stage")
