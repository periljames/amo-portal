"""Add roster consent and regulatory exemption governance.

Revision ID: rostering_260817_consent
Revises: rostering_260817_pay_merge
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_260817_consent"
down_revision = "rostering_260817_pay_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
