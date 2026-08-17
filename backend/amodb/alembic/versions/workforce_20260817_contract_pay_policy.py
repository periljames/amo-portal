"""Persist non-lowerable contract pay multiplier floors.

Revision ID: workforce_260817_pay_policy
Revises: rostering_20260815_pattern_scope
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "workforce_260817_pay_policy"
down_revision = "rostering_20260815_pattern_scope"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("employment_contract_pay_policies"):
        return
    op.create_table(
        "employment_contract_pay_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("normal_duty_multiplier", sa.Numeric(6, 3), nullable=False, server_default="1.000"),
        sa.Column("ordinary_ot_multiplier", sa.Numeric(6, 3), nullable=False, server_default="1.500"),
        sa.Column("rest_day_multiplier", sa.Numeric(6, 3), nullable=False, server_default="2.000"),
        sa.Column("public_holiday_multiplier", sa.Numeric(6, 3), nullable=False, server_default="2.000"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("normal_duty_multiplier >= 1.000", name="ck_contract_pay_normal_floor"),
        sa.CheckConstraint("ordinary_ot_multiplier >= 1.500", name="ck_contract_pay_ot_floor"),
        sa.CheckConstraint("rest_day_multiplier >= 2.000", name="ck_contract_pay_rest_floor"),
        sa.CheckConstraint("public_holiday_multiplier >= 2.000", name="ck_contract_pay_ph_floor"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["employment_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "contract_id", name="uq_contract_pay_policy_contract"),
    )
    op.create_index("ix_contract_pay_policy_amo", "employment_contract_pay_policies", ["amo_id"], unique=False)
    op.create_index("ix_contract_pay_policy_contract", "employment_contract_pay_policies", ["contract_id"], unique=False)


def downgrade() -> None:
    if not _has_table("employment_contract_pay_policies"):
        return
    op.drop_index("ix_contract_pay_policy_contract", table_name="employment_contract_pay_policies")
    op.drop_index("ix_contract_pay_policy_amo", table_name="employment_contract_pay_policies")
    op.drop_table("employment_contract_pay_policies")
