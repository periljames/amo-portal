"""Compatibility marker for workstations that already stamped phase2_14a_20260615.

Revision ID: phase2_14a_20260615
Revises: phase2_14_20260615
Create Date: 2026-06-15

This no-op migration repairs Alembic environments where the database
alembic_version table already contains phase2_14a_20260615, but the file was
removed during cleanup. Do not delete this file while any deployed database may
still reference this revision.
"""
from __future__ import annotations

revision = "phase2_14a_20260615"
down_revision = "phase2_14_20260615"
branch_labels = None
depends_on = None


def upgrade() -> None:
    return None


def downgrade() -> None:
    return None
