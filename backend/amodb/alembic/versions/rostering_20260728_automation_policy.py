"""Add tenant roster-generation policy and immutable automation runs.

Revision ID: rostering_20260728_automation_policy
Revises: rostering_20260724_governance
Create Date: 2026-07-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_20260728_automation_policy"
down_revision = "rostering_20260724_governance"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if not _has_table("roster_generation_policies"):
        op.create_table(
            "roster_generation_policies",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("frequency", sa.String(length=32), nullable=False, server_default="MONTHLY"),
            sa.Column("lead_periods", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("run_day", sa.Integer(), nullable=False, server_default="15"),
            sa.Column("run_hour_local", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("timezone_name", sa.String(length=64), nullable=False, server_default="UTC"),
            sa.Column("period_code_pattern", sa.String(length=128), nullable=False, server_default="{YYYY}-{MM}"),
            sa.Column("period_name_pattern", sa.String(length=255), nullable=False, server_default="{MMMM} {YYYY} duty roster"),
            sa.Column("create_initial_draft", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("generate_from_patterns", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("preserve_source_commitments", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("validate_after_generation", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notify_planners", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("require_preview_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("state_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_reason", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("lead_periods >= 1 AND lead_periods <= 12", name="ck_roster_generation_policy_lead"),
            sa.CheckConstraint("run_day >= 1 AND run_day <= 28", name="ck_roster_generation_policy_run_day"),
            sa.CheckConstraint("run_hour_local >= 0 AND run_hour_local <= 23", name="ck_roster_generation_policy_run_hour"),
            sa.CheckConstraint("state_revision >= 1", name="ck_roster_generation_policy_revision"),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("amo_id", name="uq_roster_generation_policy_amo"),
        )
        op.create_index(
            "ix_roster_generation_policy_enabled",
            "roster_generation_policies",
            ["enabled", "next_run_at"],
            unique=False,
        )

    if not _has_table("roster_generation_runs"):
        op.create_table(
            "roster_generation_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("policy_id", sa.String(length=36), nullable=False),
            sa.Column("trigger", sa.String(length=32), nullable=False, server_default="MANUAL"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="RUNNING"),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("period_id", sa.String(length=36), nullable=True),
            sa.Column("version_id", sa.String(length=36), nullable=True),
            sa.Column("target_from", sa.String(length=10), nullable=False),
            sa.Column("target_to", sa.String(length=10), nullable=False),
            sa.Column("generated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("validation_blocker_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("validation_warning_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary_json", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("generated_count >= 0", name="ck_roster_generation_run_generated"),
            sa.CheckConstraint("skipped_count >= 0", name="ck_roster_generation_run_skipped"),
            sa.CheckConstraint("conflict_count >= 0", name="ck_roster_generation_run_conflicts"),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["policy_id"], ["roster_generation_policies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["period_id"], ["roster_periods.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["version_id"], ["roster_versions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_roster_generation_run_idempotency"),
        )
        op.create_index(
            "ix_roster_generation_runs_amo_created",
            "roster_generation_runs",
            ["amo_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_roster_generation_runs_status",
            "roster_generation_runs",
            ["amo_id", "status"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("roster_generation_runs"):
        op.drop_index("ix_roster_generation_runs_status", table_name="roster_generation_runs")
        op.drop_index("ix_roster_generation_runs_amo_created", table_name="roster_generation_runs")
        op.drop_table("roster_generation_runs")
    if _has_table("roster_generation_policies"):
        op.drop_index("ix_roster_generation_policy_enabled", table_name="roster_generation_policies")
        op.drop_table("roster_generation_policies")
