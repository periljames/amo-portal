"""Widen Alembic revision storage before descriptive Quality revision IDs.

Revision ID: qms_vernum_128
Revises: qual_20260704_schedfix
Create Date: 2026-08-04
"""
from alembic import op


revision = "qms_vernum_128"
down_revision = "qual_20260704_schedfix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow current and future descriptive revision identifiers on PostgreSQL."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(128)"
        )


def downgrade() -> None:
    """Do not shrink shared migration metadata and truncate deployed revisions."""
    pass
