"""add training auditor access grants

Revision ID: training_20260627_auditor_access
Revises: aa11bb22cc33
Create Date: 2026-06-27 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "training_20260627_auditor_access"
down_revision: Union[str, Sequence[str], None] = "aa11bb22cc33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_auditor_access_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False, server_default="USER_TRAINING_PROFILE"),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("target_record_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("access_code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.CheckConstraint("max_uses IS NULL OR max_uses > 0", name="ck_training_auditor_access_max_uses_positive"),
        sa.CheckConstraint("use_count >= 0", name="ck_training_auditor_access_use_count_nonneg"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_record_id"], ["training_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_training_auditor_access_amo_user", "training_auditor_access_grants", ["amo_id", "target_user_id", "expires_at"], unique=False)
    op.create_index("idx_training_auditor_access_token", "training_auditor_access_grants", ["token_hash"], unique=False)
    op.create_index("idx_training_auditor_access_code", "training_auditor_access_grants", ["access_code_hash"], unique=False)
    op.create_index("idx_training_auditor_access_expires", "training_auditor_access_grants", ["expires_at"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_amo_id"), "training_auditor_access_grants", ["amo_id"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_created_by_user_id"), "training_auditor_access_grants", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_purpose"), "training_auditor_access_grants", ["purpose"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_revoked_at"), "training_auditor_access_grants", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_target_record_id"), "training_auditor_access_grants", ["target_record_id"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_target_user_id"), "training_auditor_access_grants", ["target_user_id"], unique=False)
    op.create_index(op.f("ix_training_auditor_access_grants_token_hash"), "training_auditor_access_grants", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_training_auditor_access_grants_token_hash"), table_name="training_auditor_access_grants")
    op.drop_index(op.f("ix_training_auditor_access_grants_target_user_id"), table_name="training_auditor_access_grants")
    op.drop_index(op.f("ix_training_auditor_access_grants_target_record_id"), table_name="training_auditor_access_grants")
    op.drop_index(op.f("ix_training_auditor_access_grants_revoked_at"), table_name="training_auditor_access_grants")
    op.drop_index(op.f("ix_training_auditor_access_grants_purpose"), table_name="training_auditor_access_grants")
    op.drop_index(op.f("ix_training_auditor_access_grants_created_by_user_id"), table_name="training_auditor_access_grants")
    op.drop_index(op.f("ix_training_auditor_access_grants_amo_id"), table_name="training_auditor_access_grants")
    op.drop_index("idx_training_auditor_access_expires", table_name="training_auditor_access_grants")
    op.drop_index("idx_training_auditor_access_code", table_name="training_auditor_access_grants")
    op.drop_index("idx_training_auditor_access_token", table_name="training_auditor_access_grants")
    op.drop_index("idx_training_auditor_access_amo_user", table_name="training_auditor_access_grants")
    op.drop_table("training_auditor_access_grants")
