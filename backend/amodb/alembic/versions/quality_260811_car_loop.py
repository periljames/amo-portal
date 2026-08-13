"""Add governed staged CAR/CAPA control-loop records.

Revision ID: quality_260811_car_loop
Revises: docctl_ai_audit_260809
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260811_car_loop"
down_revision = "docctl_ai_audit_260809"
branch_labels = None
depends_on = None


TABLES = (
    "quality_car_control_profiles",
    "quality_car_milestones",
    "quality_car_dependencies",
    "quality_car_deadline_changes",
    "quality_car_control_events",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY {policy}
            ON "{table_name}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            """
        )
    )


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        "quality_car_control_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("car_id", sa.Uuid(), nullable=False),
        sa.Column("accountable_owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("original_due_date", sa.Date(), nullable=False),
        sa.Column("current_due_date", sa.Date(), nullable=False),
        sa.Column("effectiveness_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("initialized_from", sa.String(length=32), server_default="CAR", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accountable_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("car_id", name="uq_quality_car_control_profile_car"),
    )
    op.create_index("ix_quality_car_control_profile_due", "quality_car_control_profiles", ["amo_id", "current_due_date"])
    op.create_index("ix_quality_car_control_profile_owner", "quality_car_control_profiles", ["amo_id", "accountable_owner_user_id"])

    op.create_table(
        "quality_car_milestones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("car_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_key", sa.String(length=40), nullable=False),
        sa.Column("phase_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("original_due_date", sa.Date(), nullable=False),
        sa.Column("current_due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="PLANNED", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_ref", sa.String(length=1024), nullable=True),
        sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "milestone_key IN ('RCA_SUBMISSION','CAP_APPROVAL','IMPLEMENTATION_COMPLETE','EVIDENCE_COMPLETE','EFFECTIVENESS_REVIEW')",
            name="ck_quality_car_milestone_key",
        ),
        sa.CheckConstraint(
            "status IN ('PLANNED','IN_PROGRESS','SUBMITTED','ACCEPTED','REJECTED','BLOCKED','COMPLETED','WAIVED')",
            name="ck_quality_car_milestone_status",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["quality_car_control_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "milestone_key", name="uq_quality_car_milestone_key"),
    )
    op.create_index("ix_quality_car_milestone_due", "quality_car_milestones", ["amo_id", "current_due_date", "status"])
    op.create_index("ix_quality_car_milestone_owner", "quality_car_milestones", ["amo_id", "owner_user_id", "status"])

    op.create_table(
        "quality_car_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("car_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dependency_type", sa.String(length=24), server_default="OTHER", nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("blocks_closure", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("mitigation_plan", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dependency_type IN ('INTERNAL','EXTERNAL','PROCUREMENT','FACILITY','RESOURCE','SUPPLIER','REGULATORY','OTHER')",
            name="ck_quality_car_dependency_type",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','MITIGATING','MITIGATED','RESOLVED','ACCEPTED_RISK','CANCELLED')",
            name="ck_quality_car_dependency_status",
        ),
        sa.CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_car_dependency_risk"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["quality_car_milestones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_car_dependency_state", "quality_car_dependencies", ["amo_id", "car_id", "status", "risk_level"])
    op.create_index("ix_quality_car_dependency_due", "quality_car_dependencies", ["amo_id", "due_date", "status"])

    op.create_table(
        "quality_car_deadline_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("car_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("previous_due_date", sa.Date(), nullable=False),
        sa.Column("requested_due_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("impact_statement", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CANCELLED')", name="ck_quality_car_deadline_change_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["quality_car_milestones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_car_deadline_change_state", "quality_car_deadline_changes", ["amo_id", "car_id", "status", "created_at"])
    op.create_index("ix_quality_car_deadline_change_milestone", "quality_car_deadline_changes", ["amo_id", "milestone_id", "status"])

    op.create_table(
        "quality_car_control_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("car_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("event_key", sa.String(length=180), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=24), server_default="INFO", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("system_generated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('INFO','ACTION_REQUIRED','WARNING','CRITICAL')", name="ck_quality_car_control_event_severity"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["milestone_id"], ["quality_car_milestones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("car_id", "event_key", name="uq_quality_car_control_event_key"),
    )
    op.create_index("ix_quality_car_control_event_timeline", "quality_car_control_events", ["amo_id", "car_id", "created_at"])
    op.create_index("ix_quality_car_control_event_type", "quality_car_control_events", ["amo_id", "event_type", "created_at"])

    for table_name in TABLES:
        _enable_rls(table_name)


def downgrade() -> None:
    for table_name in reversed(TABLES):
        _disable_rls(table_name)

    op.drop_index("ix_quality_car_control_event_type", table_name="quality_car_control_events")
    op.drop_index("ix_quality_car_control_event_timeline", table_name="quality_car_control_events")
    op.drop_table("quality_car_control_events")

    op.drop_index("ix_quality_car_deadline_change_milestone", table_name="quality_car_deadline_changes")
    op.drop_index("ix_quality_car_deadline_change_state", table_name="quality_car_deadline_changes")
    op.drop_table("quality_car_deadline_changes")

    op.drop_index("ix_quality_car_dependency_due", table_name="quality_car_dependencies")
    op.drop_index("ix_quality_car_dependency_state", table_name="quality_car_dependencies")
    op.drop_table("quality_car_dependencies")

    op.drop_index("ix_quality_car_milestone_owner", table_name="quality_car_milestones")
    op.drop_index("ix_quality_car_milestone_due", table_name="quality_car_milestones")
    op.drop_table("quality_car_milestones")

    op.drop_index("ix_quality_car_control_profile_owner", table_name="quality_car_control_profiles")
    op.drop_index("ix_quality_car_control_profile_due", table_name="quality_car_control_profiles")
    op.drop_table("quality_car_control_profiles")
