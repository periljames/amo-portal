"""Add governed programme kinds and recurring calendar-date scheduling.

Revision ID: quality_260904_prog_dates
Revises: quality_260904_purge_guards
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260904_prog_dates"
down_revision = "quality_260904_purge_guards"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        "quality_audit_programmes",
        sa.Column("programme_kind", sa.String(length=16), nullable=False, server_default="INTERNAL"),
    )
    op.execute(sa.text("""
        UPDATE quality_audit_programmes
        SET programme_kind = CASE
            WHEN lower(title) LIKE 'external audit%' THEN 'EXTERNAL'
            WHEN lower(title) LIKE 'third party audit%' THEN 'THIRD_PARTY'
            ELSE 'INTERNAL'
        END
    """))
    op.create_check_constraint(
        "ck_quality_audit_programme_kind",
        "quality_audit_programmes",
        "programme_kind IN ('INTERNAL','EXTERNAL','THIRD_PARTY')",
    )

    op.drop_constraint(
        "ck_quality_audit_programme_item_recurrence",
        "quality_audit_programme_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_item_recurrence",
        "quality_audit_programme_items",
        "recurrence IN ('ONE_TIME','MONTHLY','QUARTERLY','SEMI_ANNUAL','ANNUAL','FIXED_DATES','CUSTOM','RISK_TRIGGERED')",
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("fixed_dates", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("non_working_day_policy", sa.String(length=24), nullable=False, server_default="NEXT_WORKING_DAY"),
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("default_start_time", sa.Time(), nullable=False, server_default=sa.text("'09:00:00'")),
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("default_end_time", sa.Time(), nullable=False, server_default=sa.text("'17:00:00'")),
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("default_duration_days", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("quality_audit_programme_items", sa.Column("default_location", sa.String(length=255), nullable=True))
    op.add_column("quality_audit_programme_items", sa.Column("lead_auditor_user_id", sa.String(length=36), nullable=True))
    op.add_column("quality_audit_programme_items", sa.Column("auditee_user_id", sa.String(length=36), nullable=True))
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("notify_auditors", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("notify_auditees", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "quality_audit_programme_items",
        sa.Column("auto_schedule", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_quality_programme_item_lead_auditor",
        "quality_audit_programme_items",
        "users",
        ["lead_auditor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_quality_programme_item_auditee",
        "quality_audit_programme_items",
        "users",
        ["auditee_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_item_non_working_day",
        "quality_audit_programme_items",
        "non_working_day_policy IN ('NEXT_WORKING_DAY')",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_item_duration",
        "quality_audit_programme_items",
        "default_duration_days >= 1 AND default_duration_days <= 90",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_item_business_hours",
        "quality_audit_programme_items",
        "default_start_time >= '09:00:00' AND default_start_time <= '17:00:00' "
        "AND default_end_time >= '09:00:00' AND default_end_time <= '17:00:00' "
        "AND default_end_time > default_start_time",
    )

    op.drop_constraint(
        "ck_quality_audit_programme_occurrence_type",
        "quality_audit_programme_occurrence_links",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_occurrence_type",
        "quality_audit_programme_occurrence_links",
        "occurrence_type IN ('CUSTOM','RISK_TRIGGERED','FIXED_DATE')",
    )


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_quality_audit_programme_occurrence_immutable "
            "ON quality_audit_programme_occurrence_links"
        ))
    op.execute(sa.text("DELETE FROM quality_audit_programme_occurrence_links WHERE occurrence_type = 'FIXED_DATE'"))
    op.execute(sa.text("UPDATE quality_audit_programme_items SET recurrence = 'ONE_TIME' WHERE recurrence = 'FIXED_DATES'"))
    op.drop_constraint(
        "ck_quality_audit_programme_occurrence_type",
        "quality_audit_programme_occurrence_links",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_programme_occurrence_type",
        "quality_audit_programme_occurrence_links",
        "occurrence_type IN ('CUSTOM','RISK_TRIGGERED')",
    )
    if _is_postgresql():
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_programme_occurrence_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_programme_occurrence_links
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_programme_occurrence_mutation()
        """))
    op.drop_constraint("ck_quality_audit_programme_item_business_hours", "quality_audit_programme_items", type_="check")
    op.drop_constraint("ck_quality_audit_programme_item_duration", "quality_audit_programme_items", type_="check")
    op.drop_constraint("ck_quality_audit_programme_item_non_working_day", "quality_audit_programme_items", type_="check")
    op.drop_constraint("fk_quality_programme_item_auditee", "quality_audit_programme_items", type_="foreignkey")
    op.drop_constraint("fk_quality_programme_item_lead_auditor", "quality_audit_programme_items", type_="foreignkey")
    for column_name in (
        "auto_schedule",
        "notify_auditees",
        "notify_auditors",
        "auditee_user_id",
        "lead_auditor_user_id",
        "default_location",
        "default_duration_days",
        "default_end_time",
        "default_start_time",
        "non_working_day_policy",
        "fixed_dates",
    ):
        op.drop_column("quality_audit_programme_items", column_name)
    op.drop_constraint("ck_quality_audit_programme_item_recurrence", "quality_audit_programme_items", type_="check")
    op.create_check_constraint(
        "ck_quality_audit_programme_item_recurrence",
        "quality_audit_programme_items",
        "recurrence IN ('ONE_TIME','MONTHLY','QUARTERLY','SEMI_ANNUAL','ANNUAL','CUSTOM','RISK_TRIGGERED')",
    )
    op.drop_constraint("ck_quality_audit_programme_kind", "quality_audit_programmes", type_="check")
    op.drop_column("quality_audit_programmes", "programme_kind")
