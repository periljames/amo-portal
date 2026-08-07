"""Merge Document Control and Reliability migration heads.

Revision ID: docgov_rel_20260807_merge
Revises: docgov_20260807_qms_audit_runtime, rel_20260807_main_merge
Create Date: 2026-08-07

This revision is intentionally schema-neutral. It converges the independently
validated Document Control/QMS and Reliability migration branches after
Reliability PR #465 entered main before Document Control PR #477.
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "docgov_rel_20260807_merge"
down_revision: Union[str, Sequence[str], None] = (
    "docgov_20260807_qms_audit_runtime",
    "rel_20260807_main_merge",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
