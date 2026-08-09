"""Merge Platform Operations and formal Reliability Programme migration heads.

Revision ID: platform_rel_20260809_merge
Revises: platform_ops_20260809_incident_lifecycle, rel_20260807_formal_docgov_merge
Create Date: 2026-08-09
"""

from __future__ import annotations


revision = "platform_rel_20260809_merge"
down_revision = (
    "platform_ops_20260809_incident_lifecycle",
    "rel_20260807_formal_docgov_merge",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Schema-neutral graph merge; both parent revisions perform the DDL."""


def downgrade() -> None:
    """Split the graph back to the two parent heads without altering schema."""
