"""P0 training gate fields

Revision ID: p0a4_training_gate_fields
Revises: p0a3_compliance_event_ledger
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "p0a4_training_gate_fields"
down_revision = "p0a3_compliance_event_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("doc_control_revision_packages", sa.Column("requires_training", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("doc_control_revision_packages", sa.Column("training_gate_policy", sa.String(length=32), nullable=False, server_default="NONE"))

    op.add_column("training_requirements", sa.Column("source_type", sa.String(length=32), nullable=True))
    op.add_column("training_requirements", sa.Column("source_id", sa.String(length=64), nullable=True))
    op.add_column("training_requirements", sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("training_requirements", sa.Column("required_by_date", sa.Date(), nullable=True))
    op.create_index("ix_training_requirements_amo_source", "training_requirements", ["amo_id", "source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_training_requirements_amo_source", table_name="training_requirements")
    op.drop_column("training_requirements", "required_by_date")
    op.drop_column("training_requirements", "blocking")
    op.drop_column("training_requirements", "source_id")
    op.drop_column("training_requirements", "source_type")
    op.drop_column("doc_control_revision_packages", "training_gate_policy")
    op.drop_column("doc_control_revision_packages", "requires_training")
