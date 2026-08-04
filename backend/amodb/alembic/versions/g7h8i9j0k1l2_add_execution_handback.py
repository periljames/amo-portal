"""add production execution and records handback

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-08-04 16:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "g7h8i9j0k1l2"
down_revision = "f6g7h8i9j0k1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_execution_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_package_id", sa.Integer(), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("package_freeze_id", sa.String(length=36), sa.ForeignKey("work_package_freezes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("shift_reference", sa.String(length=64), nullable=True),
        sa.Column("station", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("started_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_sessions_amo_status", "production_execution_sessions", ["amo_id", "status"])
    op.create_index("ix_execution_sessions_package", "production_execution_sessions", ["work_package_id", "started_at"])

    op.create_table(
        "production_execution_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("production_execution_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_card_id", sa.Integer(), sa.ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_events_session_time", "production_execution_events", ["session_id", "occurred_at"])
    op.create_index("ix_execution_events_task", "production_execution_events", ["task_card_id", "occurred_at"])

    op.create_table(
        "production_task_issues",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("production_execution_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_card_id", sa.Integer(), sa.ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="MEDIUM"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("disposition", sa.String(length=32), nullable=True),
        sa.Column("linked_non_routine_task_id", sa.Integer(), sa.ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("raised_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_task_issues_session_status", "production_task_issues", ["session_id", "status"])
    op.create_index("ix_task_issues_amo_severity", "production_task_issues", ["amo_id", "severity", "status"])

    op.create_table(
        "records_handback_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_package_id", sa.Integer(), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_freeze_id", sa.String(length=36), sa.ForeignKey("work_package_freezes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("readiness_json", sa.JSON(), nullable=False),
        sa.Column("submitted_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("work_package_id", "version", name="uq_handback_package_version"),
    )
    op.create_index("ix_handback_packages_amo_status", "records_handback_packages", ["amo_id", "status"])
    op.create_index("ix_handback_packages_package", "records_handback_packages", ["work_package_id", "version"])

    op.create_table(
        "records_handback_findings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("handback_id", sa.String(length=36), sa.ForeignKey("records_handback_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="ERROR"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("response_notes", sa.Text(), nullable=True),
        sa.Column("raised_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_handback_findings_handback_status", "records_handback_findings", ["handback_id", "status"])

    op.create_table(
        "records_handback_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("handback_id", sa.String(length=36), sa.ForeignKey("records_handback_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_handback_events_handback_time", "records_handback_events", ["handback_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_handback_events_handback_time", table_name="records_handback_events")
    op.drop_table("records_handback_events")
    op.drop_index("ix_handback_findings_handback_status", table_name="records_handback_findings")
    op.drop_table("records_handback_findings")
    op.drop_index("ix_handback_packages_package", table_name="records_handback_packages")
    op.drop_index("ix_handback_packages_amo_status", table_name="records_handback_packages")
    op.drop_table("records_handback_packages")
    op.drop_index("ix_task_issues_amo_severity", table_name="production_task_issues")
    op.drop_index("ix_task_issues_session_status", table_name="production_task_issues")
    op.drop_table("production_task_issues")
    op.drop_index("ix_execution_events_task", table_name="production_execution_events")
    op.drop_index("ix_execution_events_session_time", table_name="production_execution_events")
    op.drop_table("production_execution_events")
    op.drop_index("ix_execution_sessions_package", table_name="production_execution_sessions")
    op.drop_index("ix_execution_sessions_amo_status", table_name="production_execution_sessions")
    op.drop_table("production_execution_sessions")
