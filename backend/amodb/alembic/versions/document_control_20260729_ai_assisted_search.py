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


_INDEXES = (
    (
        "ix_manual_blocks_text_search",
        "manual_blocks",
        "to_tsvector('simple', coalesce(text_plain, ''))",
    ),
    (
        "ix_manual_sections_heading_search",
        "manual_sections",
        "to_tsvector('simple', coalesce(heading, ''))",
    ),
    (
        "ix_manuals_identity_search",
        "manuals",
        "to_tsvector('simple', coalesce(code, '') || ' ' || coalesce(title, '') || ' ' || coalesce(manual_type, ''))",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Large controlled libraries must remain writable while indexes are built.
    # PostgreSQL requires concurrent index DDL outside a transaction, so Alembic's
    # explicit autocommit block is used instead of weakening the global migration
    # transaction policy.
    with op.get_context().autocommit_block():
        for name, table, expression in _INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON {table} USING GIN ({expression})"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for name, _table, _expression in reversed(_INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
