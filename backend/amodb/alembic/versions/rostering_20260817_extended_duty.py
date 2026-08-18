"""Add governed unscheduled-aircraft duty extensions.

Revision ID: rostering_260817_extension
Revises: rostering_260817_consent
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_260817_extension"
down_revision = "rostering_260817_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roster_duty_extensions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignment_id", sa.String(36), sa.ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_id", sa.String(36), sa.ForeignKey("roster_assignment_consents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("extension_type", sa.String(64), nullable=False),
        sa.Column("aircraft_registration", sa.String(32), nullable=False),
        sa.Column("operational_reference", sa.String(255), nullable=False),
        sa.Column("work_order_reference", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("normal_duty_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_planned_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proposed_extended_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("continuous_duty_minutes", sa.Integer(), nullable=False),
        sa.Column("required_recovery_rest_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_rest_basis", sa.String(255), nullable=True),
        sa.Column("compliance_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("fatigue_risk_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("proposed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("proposed_extended_end > original_planned_end", name="ck_roster_duty_extension_end_after_original"),
        sa.CheckConstraint("continuous_duty_minutes > 0", name="ck_roster_duty_extension_continuous_positive"),
        sa.CheckConstraint("required_recovery_rest_minutes >= 0", name="ck_roster_duty_extension_recovery_nonneg"),
    )
    op.create_index("ix_roster_duty_extension_amo_status", "roster_duty_extensions", ["amo_id", "status"])
    op.create_index("ix_roster_duty_extension_assignment", "roster_duty_extensions", ["assignment_id", "created_at"])


def downgrade() -> None:
    pass
