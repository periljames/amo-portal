"""Merge Workforce contract pay policy with the current application head.

Revision ID: rostering_260817_pay_merge
Revises: resilience_260816_commands, workforce_260817_pay_policy
Create Date: 2026-08-17
"""
from __future__ import annotations


revision = "rostering_260817_pay_merge"
down_revision = (
    "resilience_260816_commands",
    "workforce_260817_pay_policy",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
