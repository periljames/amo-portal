"""Add roster consent governance.

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
    op.add_column("roster_shift_template_policies", sa.Column("requires_personnel_acknowledgement", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("roster_shift_template_policies", sa.Column("requires_supervisor_approval", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("roster_shift_template_policies", sa.Column("fatigue_weight", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("roster_shift_template_policies", sa.Column("pay_classification", sa.String(length=64), nullable=True))


def downgrade() -> None:
    pass
