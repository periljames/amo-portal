"""Link governed audit programme requirements to authoritative planner schedules.

Revision ID: quality_260808_prog_schedule
Revises: quality_260808_audit_programme
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260808_prog_schedule"
down_revision = "quality_260808_audit_programme"
branch_labels = None
depends_on = None


_EVENT_TYPES = (
    "'CREATED','UPDATED','SUBMITTED_FOR_REVIEW','RETURNED_TO_DRAFT','APPROVED','ACTIVATED',"
    "'AMENDMENT_CREATED','SUPERSEDED','CLOSED','ITEM_ADDED','ITEM_UPDATED','ITEM_SCHEDULED'"
)


def upgrade() -> None:
    with op.batch_alter_table("quality_audit_programme_items") as batch:
        batch.add_column(sa.Column("schedule_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("scheduled_by_user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_quality_audit_programme_item_schedule",
            "qms_audit_schedules",
            ["schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_quality_audit_programme_item_scheduled_by",
            "users",
            ["scheduled_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint("uq_quality_audit_programme_item_schedule", ["schedule_id"])

    op.create_index(
        "ix_quality_audit_programme_items_schedule",
        "quality_audit_programme_items",
        ["amo_id", "schedule_id", "state"],
    )

    with op.batch_alter_table("quality_audit_programme_events") as batch:
        batch.drop_constraint("ck_quality_audit_programme_event_type", type_="check")
        batch.create_check_constraint(
            "ck_quality_audit_programme_event_type",
            f"event_type IN ({_EVENT_TYPES})",
        )


def downgrade() -> None:
    with op.batch_alter_table("quality_audit_programme_events") as batch:
        batch.drop_constraint("ck_quality_audit_programme_event_type", type_="check")
        batch.create_check_constraint(
            "ck_quality_audit_programme_event_type",
            "event_type IN ('CREATED','UPDATED','SUBMITTED_FOR_REVIEW','RETURNED_TO_DRAFT','APPROVED','ACTIVATED','AMENDMENT_CREATED','SUPERSEDED','CLOSED','ITEM_ADDED','ITEM_UPDATED')",
        )

    op.drop_index("ix_quality_audit_programme_items_schedule", table_name="quality_audit_programme_items")
    with op.batch_alter_table("quality_audit_programme_items") as batch:
        batch.drop_constraint("uq_quality_audit_programme_item_schedule", type_="unique")
        batch.drop_constraint("fk_quality_audit_programme_item_scheduled_by", type_="foreignkey")
        batch.drop_constraint("fk_quality_audit_programme_item_schedule", type_="foreignkey")
        batch.drop_column("scheduled_at")
        batch.drop_column("scheduled_by_user_id")
        batch.drop_column("schedule_id")
