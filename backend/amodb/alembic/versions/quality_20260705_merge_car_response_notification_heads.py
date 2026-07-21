"""Merge July 2026 quality repair branches.

Revision ID: qual_20260705_merge_heads
Revises: qual_20260704_carattach, qual_20260704_carresp, quality_20260705_car_attachment_description, quality_20260705_notification_action_links, quality_20260705_finding_attachment_description_repair
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "qual_20260705_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "qual_20260704_carattach",
    "qual_20260704_carresp",
    "quality_20260705_car_attachment_description",
    "quality_20260705_notification_action_links",
    "quality_20260705_finding_attachment_description_repair",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
