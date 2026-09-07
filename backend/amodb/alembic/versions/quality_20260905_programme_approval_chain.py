"""Record the audit programme approval chain.

Revision ID: quality_260905_prog_approval
Revises: quality_260905_programme_team
Create Date: 2026-09-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260905_prog_approval"
down_revision = "quality_260905_programme_team"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_audit_programmes",
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "quality_audit_programmes",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "quality_audit_programmes",
        sa.Column("quality_reviewed_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "quality_audit_programmes",
        sa.Column("quality_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quality_audit_programmes_submitted_by",
        "quality_audit_programmes",
        "users",
        ["submitted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_quality_audit_programmes_quality_reviewed_by",
        "quality_audit_programmes",
        "users",
        ["quality_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "ck_quality_audit_programme_event_type",
        "quality_audit_programme_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_event_type",
        "quality_audit_programme_events",
        "event_type IN ('CREATED','UPDATED','SUBMITTED_FOR_REVIEW','QUALITY_REVIEW_COMPLETED',"
        "'RETURNED_TO_DRAFT','APPROVED','ACTIVATED','AMENDMENT_CREATED','SUPERSEDED','CLOSED',"
        "'ITEM_ADDED','ITEM_UPDATED','ITEM_SCHEDULED')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_quality_audit_programme_event_type",
        "quality_audit_programme_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_event_type",
        "quality_audit_programme_events",
        "event_type IN ('CREATED','UPDATED','SUBMITTED_FOR_REVIEW','RETURNED_TO_DRAFT','APPROVED',"
        "'ACTIVATED','AMENDMENT_CREATED','SUPERSEDED','CLOSED','ITEM_ADDED','ITEM_UPDATED','ITEM_SCHEDULED')",
    )
    op.drop_constraint(
        "fk_quality_audit_programmes_quality_reviewed_by",
        "quality_audit_programmes",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_quality_audit_programmes_submitted_by",
        "quality_audit_programmes",
        type_="foreignkey",
    )
    op.drop_column("quality_audit_programmes", "quality_reviewed_at")
    op.drop_column("quality_audit_programmes", "quality_reviewed_by_user_id")
    op.drop_column("quality_audit_programmes", "submitted_at")
    op.drop_column("quality_audit_programmes", "submitted_by_user_id")
