"""Add roster consent governance.

Revision ID: rostering_260817_consent
Revises: rostering_260817_pay_merge
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_260817_consent"
down_revision = "rostering_260817_pay_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roster_shift_template_policies", sa.Column("requires_personnel_acknowledgement", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("roster_shift_template_policies", sa.Column("requires_supervisor_approval", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("roster_shift_template_policies", sa.Column("fatigue_weight", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("roster_shift_template_policies", sa.Column("pay_classification", sa.String(length=64), nullable=True))
    op.create_table(
        "roster_assignment_consents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignment_id", sa.String(36), sa.ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignment_revision", sa.Integer(), nullable=False),
        sa.Column("assignment_fingerprint", sa.String(64), nullable=False),
        sa.Column("personnel_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("duty_type", sa.String(64), nullable=False),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_schedule_json", sa.JSON(), nullable=True),
        sa.Column("personnel_response", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("personnel_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("personnel_comment", sa.Text(), nullable=True),
        sa.Column("supervisor_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supervisor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supervisor_decision", sa.String(32), nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("supervisor_decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supervisor_decided_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supervisor_comment", sa.Text(), nullable=True),
        sa.Column("overtime_rest_day_classification", sa.String(64), nullable=True),
        sa.Column("replacement_rest_json", sa.JSON(), nullable=True),
        sa.Column("statutory_compliance_json", sa.JSON(), nullable=True),
        sa.Column("fatigue_risk_json", sa.JSON(), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("assignment_revision >= 1", name="ck_roster_consent_revision_positive"),
        sa.CheckConstraint("planned_end > planned_start", name="ck_roster_consent_time_order"),
        sa.UniqueConstraint("assignment_id", "assignment_revision", name="uq_roster_assignment_consent_revision"),
    )
    op.create_index("ix_roster_consent_amo_personnel_status", "roster_assignment_consents", ["amo_id", "personnel_id", "personnel_response"])
    op.create_index("ix_roster_consent_version_status", "roster_assignment_consents", ["version_id", "personnel_response", "supervisor_decision"])


def downgrade() -> None:
    pass
