"""Merge rostering wage-order and Workforce contract-pay-policy heads.

Revision ID: rostering_20260817_pay_merge
Revises: rostering_20260817_wage_orders, workforce_20260817_contract_pay_policy
Create Date: 2026-08-17

Both parent revisions are independently valid schema changes.  Keep both
histories intact and restore the repository invariant of one authoritative
Alembic head rather than rewriting either already-created migration.
"""
from __future__ import annotations


revision = "rostering_20260817_pay_merge"
down_revision = (
    "rostering_20260817_wage_orders",
    "workforce_20260817_contract_pay_policy",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
