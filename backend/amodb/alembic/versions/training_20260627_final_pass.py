"""training final report settings and QR verification

Revision ID: train_20260627_final
Revises: training_20260627_auditor_access
Create Date: 2026-06-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "train_20260627_final"
down_revision: Union[str, Sequence[str], None] = "training_20260627_auditor_access"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _insp().has_table(name)


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {idx["name"] for idx in _insp().get_indexes(table)}


def upgrade() -> None:
    if not _has_table("training_report_settings"):
        op.create_table(
            "training_report_settings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False, server_default="Personnel Training Record"),
            sa.Column("subtitle", sa.Text(), nullable=True),
            sa.Column("form_no", sa.String(length=64), nullable=False, server_default="QAM/49A"),
            sa.Column("issue_date", sa.String(length=64), nullable=False, server_default="1 Sept 25"),
            sa.Column("revision", sa.String(length=32), nullable=False, server_default="00"),
            sa.Column("show_compliance_summary", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_training_history", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_scheduled_events", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_deferrals", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("footer_note", sa.Text(), nullable=True),
            sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("amo_id", name="uq_training_report_settings_amo"),
        )
    if _has_table("training_report_settings") and not _has_index("training_report_settings", "idx_training_report_settings_amo"):
        op.create_index("idx_training_report_settings_amo", "training_report_settings", ["amo_id"], unique=False)


def downgrade() -> None:
    if _has_table("training_report_settings"):
        if _has_index("training_report_settings", "idx_training_report_settings_amo"):
            op.drop_index("idx_training_report_settings_amo", table_name="training_report_settings")
        op.drop_table("training_report_settings")
