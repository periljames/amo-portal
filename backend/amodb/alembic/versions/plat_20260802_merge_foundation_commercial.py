"""merge foundation geofence and commercial control heads

Revision ID: plat_20260802_merge_heads
Revises: foundation_20260731_geofence, plat_20260801_commercial_v2
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "plat_20260802_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "foundation_20260731_geofence",
    "plat_20260801_commercial_v2",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Join the two independently safe migration branches."""


def downgrade() -> None:
    """Return to the two predecessor heads."""
