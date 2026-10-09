"""Add structured context to governed audit evidence artifacts.

Revision ID: quality_261003_evidence_context
Revises: quality_261002_applicability_ctx
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "quality_261003_evidence_context"
down_revision = "quality_261002_applicability_ctx"
branch_labels = None
depends_on = None

TABLE = "quality_audit_evidence_artifacts"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return set()
    return {column["name"] for column in inspector.get_columns(TABLE)}


def upgrade() -> None:
    if "context_json" not in _columns():
        op.add_column(
            TABLE,
            sa.Column(
                "context_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    if "context_json" in _columns():
        op.drop_column(TABLE, "context_json")
