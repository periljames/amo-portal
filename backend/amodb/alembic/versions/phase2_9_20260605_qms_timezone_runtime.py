"""QMS timezone runtime bridge migration.

Revision ID: phase2_9_20260605
Revises: phase2_5_20260605
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op

revision = "phase2_9_20260605"
down_revision = "phase2_5_20260605"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bridge migration retained to repair deployments where phase2_10 referenced
    # phase2_9 but the file was not present. Runtime timezone support uses the
    # existing amos.time_zone column and does not require schema changes here.
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
