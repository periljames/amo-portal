"""add reliability notifications and reports

Revision ID: d1a2f3b4c5e6
Revises: c4d2a7b9f1e0
Create Date: 2025-02-14 00:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d1a2f3b4c5e6"
down_revision: Union[str, Sequence[str], None] = "c4d2a7b9f1e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reliability_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("alert_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="reliability_notification_severity_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["reliability_alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "user_id", "dedupe_key", name="uq_reliability_notifications_dedupe"),
    )
    op.create_index(
        op.f("ix_reliability_notifications_amo_id"),
        "reliability_notifications",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reliability_notifications_user_id"),
        "reliability_notifications",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reliability_notifications_department_id"),
        "reliability_notifications",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reliability_notifications_alert_id"),
        "reliability_notifications",
        ["alert_id"],
        unique=False,
    )
    op.create_index(
        "ix_reliability_notifications_amo_user",
        "reliability_notifications",
        ["amo_id", "user_id"],
        unique=False,
    )

    op.create_table(
        "reliability_notification_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "SUPERUSER",
                "AMO_ADMIN",
                "QUALITY_MANAGER",
                "SAFETY_MANAGER",
                "PLANNING_ENGINEER",
                "PRODUCTION_ENGINEER",
                "CERTIFYING_ENGINEER",
                "CERTIFYING_TECHNICIAN",
                "TECHNICIAN",
                "STORES",
                "VIEW_ONLY",
                name="reliability_notification_role_enum",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="reliability_notification_rule_severity_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reliability_notification_rules_amo",
        "reliability_notification_rules",
        ["amo_id", "severity"],
        unique=False,
    )

    op.create_table(
        "reliability_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "READY", "FAILED", name="reliability_report_status_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("file_ref", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reliability_reports_amo_window",
        "reliability_reports",
        ["amo_id", "window_start", "window_end"],
        unique=False,
    )
    op.create_index(op.f("ix_reliability_reports_amo_id"), "reliability_reports", ["amo_id"], unique=False)
    op.create_index(op.f("ix_reliability_reports_window_start"), "reliability_reports", ["window_start"], unique=False)
    op.create_index(op.f("ix_reliability_reports_window_end"), "reliability_reports", ["window_end"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reliability_reports_window_end"), table_name="reliability_reports")
    op.drop_index(op.f("ix_reliability_reports_window_start"), table_name="reliability_reports")
    op.drop_index(op.f("ix_reliability_reports_amo_id"), table_name="reliability_reports")
    op.drop_index("ix_reliability_reports_amo_window", table_name="reliability_reports")
    op.drop_table("reliability_reports")

    op.drop_index("ix_reliability_notification_rules_amo", table_name="reliability_notification_rules")
    op.drop_table("reliability_notification_rules")

    op.drop_index("ix_reliability_notifications_amo_user", table_name="reliability_notifications")
    op.drop_index(op.f("ix_reliability_notifications_alert_id"), table_name="reliability_notifications")
    op.drop_index(op.f("ix_reliability_notifications_department_id"), table_name="reliability_notifications")
    op.drop_index(op.f("ix_reliability_notifications_user_id"), table_name="reliability_notifications")
    op.drop_index(op.f("ix_reliability_notifications_amo_id"), table_name="reliability_notifications")
    op.drop_table("reliability_notifications")
