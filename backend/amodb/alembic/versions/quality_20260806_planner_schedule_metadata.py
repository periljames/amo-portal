"""Add governed metadata for authoritative Quality planner commitments.

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
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("source_schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("timezone_name", sa.String(length=64), nullable=False, server_default="Africa/Nairobi"),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("responsible_user_id", sa.String(length=36), nullable=True),
        sa.Column("attendee_user_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("external_attendees_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("notify_attendees", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lifecycle_status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("suspension_reason", sa.Text(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "(source_type IS NULL AND source_id IS NULL) OR "
            "(source_type IS NOT NULL AND source_id IS NOT NULL)",
            name="ck_qms_planner_metadata_source_pair",
        ),
        sa.CheckConstraint(
            "(CASE WHEN schedule_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN audit_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN source_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_qms_planner_metadata_single_subject",
        ),
        sa.CheckConstraint(
            "source_type IS NULL OR source_type IN "
            "('CAR','CAPA','TRAINING_EVENT','MANAGEMENT_REVIEW','OTHER_QMS_COMMITMENT')",
            name="ck_qms_planner_metadata_source_type",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('ACTIVE','SUSPENDED','CANCELLED','COMPLETED')",
            name="ck_qms_planner_metadata_lifecycle",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR occurrence_date IS NULL OR end_date >= occurrence_date",
            name="ck_qms_planner_metadata_date_order",
        ),
        sa.CheckConstraint("version >= 1", name="ck_qms_planner_metadata_version"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["qms_audit_schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_schedule_id"], ["qms_audit_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["suspended_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_qms_planner_schedule_metadata"),
        sa.UniqueConstraint("amo_id", "schedule_id", name="uq_qms_planner_metadata_schedule"),
        sa.UniqueConstraint("amo_id", "audit_id", name="uq_qms_planner_metadata_audit"),
        sa.UniqueConstraint("amo_id", "source_type", "source_id", name="uq_qms_planner_metadata_source"),
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
    op.create_index("ix_qms_planner_schedule_metadata_source_type", "qms_planner_schedule_metadata", ["source_type"])
    op.create_index("ix_qms_planner_schedule_metadata_source_id", "qms_planner_schedule_metadata", ["source_id"])
    op.create_index("ix_qms_planner_schedule_metadata_source_schedule_id", "qms_planner_schedule_metadata", ["source_schedule_id"])
    op.create_index("ix_qms_planner_schedule_metadata_occurrence_date", "qms_planner_schedule_metadata", ["occurrence_date"])
    op.create_index("ix_qms_planner_schedule_metadata_end_date", "qms_planner_schedule_metadata", ["end_date"])
    op.create_index("ix_qms_planner_schedule_metadata_responsible_user_id", "qms_planner_schedule_metadata", ["responsible_user_id"])
    op.create_index("ix_qms_planner_schedule_metadata_lifecycle_status", "qms_planner_schedule_metadata", ["lifecycle_status"])
    op.create_index(
        "ix_qms_planner_metadata_amo_occurrence",
        "qms_planner_schedule_metadata",
        ["amo_id", "occurrence_date"],
    )
    op.create_index(
        "ix_qms_planner_metadata_amo_lifecycle",
        "qms_planner_schedule_metadata",
        ["amo_id", "lifecycle_status"],
    )
    op.create_index(
        "ix_qms_planner_metadata_amo_source",
        "qms_planner_schedule_metadata",
        ["amo_id", "source_type", "source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_qms_planner_metadata_amo_source", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_metadata_amo_lifecycle", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_metadata_amo_occurrence", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_lifecycle_status", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_responsible_user_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_end_date", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_occurrence_date", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_source_schedule_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_source_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_source_type", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_audit_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_schedule_id", table_name="qms_planner_schedule_metadata")
    op.drop_index("ix_qms_planner_schedule_metadata_amo_id", table_name="qms_planner_schedule_metadata")
    op.drop_table("qms_planner_schedule_metadata")
