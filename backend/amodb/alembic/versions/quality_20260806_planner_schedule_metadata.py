"""Add timed metadata for authoritative Quality planner schedules.

Revision ID: quality_20260806_planner_metadata
Revises: rel_quality_20260804_merge
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "quality_20260806_planner_metadata"
down_revision: Union[str, Sequence[str], None] = "rel_quality_20260804_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qms_planner_schedule_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("timezone_name", sa.String(length=64), nullable=False, server_default="Africa/Nairobi"),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attendee_user_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("external_attendees_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["qms_audit_schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_schedule_id"], ["qms_audit_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_qms_planner_schedule_metadata"),
        sa.UniqueConstraint("amo_id", "schedule_id", name="uq_qms_planner_metadata_schedule"),
        sa.UniqueConstraint("amo_id", "audit_id", name="uq_qms_planner_metadata_audit"),
        sa.UniqueConstraint(
            "amo_id",
            "source_schedule_id",
            "occurrence_date",
            name="uq_qms_planner_metadata_occurrence",
        ),
    )
    op.create_index("ix_qms_planner_schedule_metadata_amo_id", "qms_planner_schedule_metadata", ["amo_id"])
    op.create_index("ix_qms_planner_schedule_metadata_schedule_id", "qms_planner_schedule_metadata", ["schedule_id"])
    op.create_index("ix_qms_planner_schedule_metadata_audit_id", "qms_planner_schedule_metadata", ["audit_id"])
    op.create_index("ix_qms_planner_schedule_metadata_source_schedule_id", "qms_planner_schedule_metadata", ["source_schedule_id"])
    op.create_index("ix_qms_planner_schedule_metadata_occurrence_date", "qms_planner_schedule_metadata", ["occurrence_date"])
    op.create_index(
        "ix_qms_planner_metadata_amo_occurrence",
        "qms_planner_schedule_metadata",
        ["amo_id", "occurrence_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_qms_planner_metadata_amo_occurrence", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_occurrence_date", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_source_schedule_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_audit_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_schedule_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_amo_id", table_name="qms_planner_schedule_metadata")
    op.drop_table("qms_planner_schedule_metadata")
