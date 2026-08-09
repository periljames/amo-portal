"""Merge Platform Operations control data with Document Governance release head.

Revision ID: platform_ops_20260809_docgov_merge
Revises: platform_ops_20260809_incident_lifecycle, docgov_rel_20260807_merge
Create Date: 2026-08-09

This is a graph-only merge. Both branches retain their complete ancestry and no
schema operation is repeated here.
"""

revision = "platform_ops_20260809_docgov_merge"
down_revision = (
    "platform_ops_20260809_incident_lifecycle",
    "docgov_rel_20260807_merge",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
