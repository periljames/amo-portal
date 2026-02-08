"""add audit schedules and auditor flag

Revision ID: t1u2v3w4x5y6
Revises: s1t2u3v4w5x6
Create Date: 2026-03-10 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "t1u2v3w4x5y6"
down_revision = "s1t2u3v4w5x6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_auditor", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("idx_users_is_auditor", "users", ["is_auditor"], unique=False)

    op.add_column("qms_audits", sa.Column("auditee_user_id", sa.String(length=36), nullable=True))
    op.add_column("qms_audits", sa.Column("checklist_file_ref", sa.String(length=512), nullable=True))
    op.add_column("qms_audits", sa.Column("upcoming_notice_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("qms_audits", sa.Column("day_of_notice_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_qms_audits_auditee_user_id", "qms_audits", ["auditee_user_id"], unique=False)
    op.create_index("ix_qms_audits_upcoming_notice", "qms_audits", ["upcoming_notice_sent_at"], unique=False)
    op.create_index("ix_qms_audits_day_of_notice", "qms_audits", ["day_of_notice_sent_at"], unique=False)
    op.create_foreign_key(
        "fk_qms_audits_auditee_user_id_users",
        "qms_audits",
        "users",
        ["auditee_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("qms_audit_findings", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("qms_audit_findings", sa.Column("acknowledged_by_user_id", sa.String(length=36), nullable=True))
    op.add_column("qms_audit_findings", sa.Column("acknowledged_by_name", sa.String(length=255), nullable=True))
    op.add_column("qms_audit_findings", sa.Column("acknowledged_by_email", sa.String(length=255), nullable=True))
    op.create_index("ix_qms_audit_findings_ack_at", "qms_audit_findings", ["acknowledged_at"], unique=False)
    op.create_index(
        "ix_qms_audit_findings_ack_user",
        "qms_audit_findings",
        ["acknowledged_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_qms_audit_findings_ack_user_id_users",
        "qms_audit_findings",
        "users",
        ["acknowledged_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    schedule_domain_enum = sa.Enum("AMO", "RELIABILITY", name="qms_audit_schedule_domain", native_enum=False)
    schedule_kind_enum = sa.Enum(
        "INTERNAL", "EXTERNAL", "THIRD_PARTY", name="qms_audit_schedule_kind", native_enum=False
    )
    schedule_frequency_enum = sa.Enum(
        "MONTHLY", "ANNUAL", name="qms_audit_schedule_frequency", native_enum=False
    )
    schedule_domain_enum.create(op.get_bind(), checkfirst=True)
    schedule_kind_enum.create(op.get_bind(), checkfirst=True)
    schedule_frequency_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "qms_audit_schedules",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("domain", schedule_domain_enum, nullable=False),
        sa.Column("kind", schedule_kind_enum, nullable=False),
        sa.Column("frequency", schedule_frequency_enum, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("auditee", sa.String(length=255), nullable=True),
        sa.Column("auditee_email", sa.String(length=255), nullable=True),
        sa.Column("auditee_user_id", sa.String(length=36), nullable=True),
        sa.Column("lead_auditor_user_id", sa.String(length=36), nullable=True),
        sa.Column("observer_auditor_user_id", sa.String(length=36), nullable=True),
        sa.Column("assistant_auditor_user_id", sa.String(length=36), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auditee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_auditor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["observer_auditor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assistant_auditor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_qms_audit_schedules_domain_active",
        "qms_audit_schedules",
        ["domain", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_qms_audit_schedules_next_due_date",
        "qms_audit_schedules",
        ["next_due_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_qms_audit_schedules_next_due_date", table_name="qms_audit_schedules")
    op.drop_index("ix_qms_audit_schedules_domain_active", table_name="qms_audit_schedules")
    op.drop_table("qms_audit_schedules")

    schedule_domain_enum = sa.Enum("AMO", "RELIABILITY", name="qms_audit_schedule_domain", native_enum=False)
    schedule_kind_enum = sa.Enum(
        "INTERNAL", "EXTERNAL", "THIRD_PARTY", name="qms_audit_schedule_kind", native_enum=False
    )
    schedule_frequency_enum = sa.Enum(
        "MONTHLY", "ANNUAL", name="qms_audit_schedule_frequency", native_enum=False
    )
    schedule_frequency_enum.drop(op.get_bind(), checkfirst=True)
    schedule_kind_enum.drop(op.get_bind(), checkfirst=True)
    schedule_domain_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_constraint("fk_qms_audit_findings_ack_user_id_users", "qms_audit_findings", type_="foreignkey")
    op.drop_index("ix_qms_audit_findings_ack_user", table_name="qms_audit_findings")
    op.drop_index("ix_qms_audit_findings_ack_at", table_name="qms_audit_findings")
    op.drop_column("qms_audit_findings", "acknowledged_by_email")
    op.drop_column("qms_audit_findings", "acknowledged_by_name")
    op.drop_column("qms_audit_findings", "acknowledged_by_user_id")
    op.drop_column("qms_audit_findings", "acknowledged_at")

    op.drop_constraint("fk_qms_audits_auditee_user_id_users", "qms_audits", type_="foreignkey")
    op.drop_index("ix_qms_audits_day_of_notice", table_name="qms_audits")
    op.drop_index("ix_qms_audits_upcoming_notice", table_name="qms_audits")
    op.drop_index("ix_qms_audits_auditee_user_id", table_name="qms_audits")
    op.drop_column("qms_audits", "day_of_notice_sent_at")
    op.drop_column("qms_audits", "upcoming_notice_sent_at")
    op.drop_column("qms_audits", "checklist_file_ref")
    op.drop_column("qms_audits", "auditee_user_id")

    op.drop_index("idx_users_is_auditor", table_name="users")
    op.drop_column("users", "is_auditor")
