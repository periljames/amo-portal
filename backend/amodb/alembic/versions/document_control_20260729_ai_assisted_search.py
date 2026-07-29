"""Add scalable controlled-document full-text indexes.

Revision ID: document_control_20260729_ai_assisted_search
Revises: document_control_20260729_knowledge_graph
Create Date: 2026-07-29

The indexes accelerate permission-filtered retrieval over existing controlled section
headings and block text. They do not copy document content to a separate store and do
not alter approved source files or revision checksums.
"""
from __future__ import annotations

from alembic import op


revision = "document_control_20260729_ai_assisted_search"
down_revision = "document_control_20260729_knowledge_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_manual_blocks_text_search
        ON manual_blocks
        USING GIN (to_tsvector('simple', coalesce(text_plain, '')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_manual_sections_heading_search
        ON manual_sections
        USING GIN (to_tsvector('simple', coalesce(heading, '')))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_manuals_identity_search
        ON manuals
        USING GIN (to_tsvector('simple', coalesce(code, '') || ' ' || coalesce(title, '') || ' ' || coalesce(manual_type, '')))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_manuals_identity_search")
    op.execute("DROP INDEX IF EXISTS ix_manual_sections_heading_search")
    op.execute("DROP INDEX IF EXISTS ix_manual_blocks_text_search")
