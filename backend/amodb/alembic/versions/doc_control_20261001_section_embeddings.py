"""Add persisted section embeddings for controlled-document hybrid retrieval.

Revision ID: docctrl_261001_section_embed
Revises: quality_261001_compliance_intel
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "docctrl_261001_section_embed"
down_revision = "quality_261001_compliance_intel"
branch_labels = None
depends_on = None

TABLE = "documentation_section_embeddings"


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE)


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("section_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_model", sa.String(length=96), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("vector_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["manual_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "revision_id",
            "section_id",
            "embedding_model",
            name="uq_documentation_section_embedding",
        ),
    )
    op.create_index(
        "ix_documentation_section_embeddings_tenant_revision",
        TABLE,
        ["tenant_id", "revision_id"],
        unique=False,
    )
    op.create_index(
        "ix_documentation_section_embeddings_section",
        TABLE,
        ["section_id", "embedding_model"],
        unique=False,
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE)
