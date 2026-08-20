"""reconcile Quality workflow tables with the active ORM contract

Revision ID: quality_260820_wf_schema
Revises: training_260818_connected_delivery
Create Date: 2026-08-20

The original June workflow-closure migration created the first versions of the
post-brief, report-tracker, reminder and archive tables. The application models
have since evolved, but those schema changes were not represented by a forward
migration. Fresh PostgreSQL databases therefore upgraded successfully while
runtime Quality queries failed on missing columns.

This migration is intentionally additive/data-preserving where practical. Old
columns are retained when they may contain historical evidence, but obsolete
NOT NULL requirements and constraints that conflict with the current ORM are
neutralised so new governed records can be inserted safely.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "quality_260820_wf_schema"
down_revision: Union[str, Sequence[str], None] = "training_260818_connected_delivery"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _insp().has_table(name)


def _columns(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {column["name"] for column in _insp().get_columns(table)}


def _indexes(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {index["name"] for index in _insp().get_indexes(table)}


def _unique_constraints(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {
        constraint["name"]
        for constraint in _insp().get_unique_constraints(table)
        if constraint.get("name")
    }


def _check_constraints(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {
        constraint["name"]
        for constraint in _insp().get_check_constraints(table)
        if constraint.get("name")
    }


def _foreign_keys(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {
        constraint["name"]
        for constraint in _insp().get_foreign_keys(table)
        if constraint.get("name")
    }


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if _has_table(table) and name not in _indexes(table):
        op.create_index(name, table, columns, unique=unique)


def _drop_index(name: str, table: str) -> None:
    if name in _indexes(table):
        op.drop_index(name, table_name=table)


def _drop_check(name: str, table: str) -> None:
    if name in _check_constraints(table):
        op.drop_constraint(name, table, type_="check")


def _drop_unique(name: str, table: str) -> None:
    if name in _unique_constraints(table):
        op.drop_constraint(name, table, type_="unique")


def _reconcile_post_briefs() -> None:
    table = "quality_audit_post_briefs"
    if not _has_table(table):
        return

    columns = _columns(table)
    if "briefing_at" not in columns:
        op.add_column(table, sa.Column("briefing_at", sa.DateTime(timezone=True), nullable=True))
    if "report_due_date" not in columns:
        op.add_column(table, sa.Column("report_due_date", sa.Date(), nullable=True))

    columns = _columns(table)
    if "brief_date" in columns:
        op.execute(sa.text(
            """
            UPDATE quality_audit_post_briefs
               SET briefing_at = COALESCE(
                       briefing_at,
                       created_at,
                       brief_date::timestamp AT TIME ZONE 'UTC',
                       NOW()
                   )
             WHERE briefing_at IS NULL
            """
        ))
        op.execute(sa.text(
            """
            UPDATE quality_audit_post_briefs AS brief
               SET report_due_date = COALESCE(
                       report_due_date,
                       brief.brief_date + COALESCE(
                           (
                               SELECT settings.report_due_days
                                 FROM quality_tenant_workflow_settings AS settings
                                WHERE settings.amo_id = brief.amo_id
                                LIMIT 1
                           ),
                           7
                       ),
                       brief.created_at::date + 7,
                       CURRENT_DATE + 7
                   )
             WHERE report_due_date IS NULL
            """
        ))
        # The active ORM no longer supplies brief_date on INSERT.
        op.alter_column(table, "brief_date", existing_type=sa.Date(), nullable=True)
    else:
        op.execute(sa.text(
            """
            UPDATE quality_audit_post_briefs
               SET briefing_at = COALESCE(briefing_at, created_at, NOW()),
                   report_due_date = COALESCE(report_due_date, created_at::date + 7, CURRENT_DATE + 7)
             WHERE briefing_at IS NULL OR report_due_date IS NULL
            """
        ))

    columns = _columns(table)
    if "summary" in columns:
        if "decisions" in columns and "follow_up_actions" in columns:
            op.execute(sa.text(
                """
                UPDATE quality_audit_post_briefs
                   SET summary = COALESCE(
                       NULLIF(BTRIM(summary), ''),
                       NULLIF(BTRIM(decisions), ''),
                       NULLIF(BTRIM(follow_up_actions), ''),
                       'Migrated audit post-brief'
                   )
                 WHERE summary IS NULL OR BTRIM(summary) = ''
                """
            ))
        else:
            op.execute(sa.text(
                """
                UPDATE quality_audit_post_briefs
                   SET summary = 'Migrated audit post-brief'
                 WHERE summary IS NULL OR BTRIM(summary) = ''
                """
            ))
        op.alter_column(table, "summary", existing_type=sa.Text(), nullable=False)

    op.alter_column(table, "briefing_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column(table, "report_due_date", existing_type=sa.Date(), nullable=False)

    # Current model is one post-brief per audit. Convert the historical
    # non-unique index into an explicit unique index so drift cannot recur.
    _drop_index("ix_quality_audit_post_briefs_audit_id", table)
    _create_index("ix_quality_audit_post_briefs_audit_id", table, ["audit_id"], unique=True)
    _create_index("ix_quality_audit_post_briefs_report_due_date", table, ["report_due_date"])
    _create_index("ix_quality_audit_post_briefs_created_by_user_id", table, ["created_by_user_id"])


def _reconcile_report_trackers() -> None:
    table = "quality_audit_report_trackers"
    if not _has_table(table):
        return

    columns = _columns(table)
    if "report_due_date" not in columns:
        op.add_column(table, sa.Column("report_due_date", sa.Date(), nullable=True))
    if "feedback_due_date" not in columns:
        op.add_column(table, sa.Column("feedback_due_date", sa.Date(), nullable=True))
    if "feedback_submitted_at" not in columns:
        op.add_column(table, sa.Column("feedback_submitted_at", sa.DateTime(timezone=True), nullable=True))
    if "created_by_user_id" not in columns:
        op.add_column(table, sa.Column("created_by_user_id", sa.String(length=36), nullable=True))

    columns = _columns(table)
    if "due_date" in columns:
        op.execute(sa.text(
            """
            UPDATE quality_audit_report_trackers
               SET report_due_date = COALESCE(report_due_date, due_date)
             WHERE report_due_date IS NULL
            """
        ))
        # Current inserts provide report_due_date, not the legacy due_date.
        op.alter_column(table, "due_date", existing_type=sa.Date(), nullable=True)
    else:
        op.execute(sa.text(
            """
            UPDATE quality_audit_report_trackers
               SET report_due_date = COALESCE(report_due_date, CURRENT_DATE)
             WHERE report_due_date IS NULL
            """
        ))

    _drop_check("ck_quality_report_tracker_status", table)
    op.execute(sa.text(
        """
        UPDATE quality_audit_report_trackers
           SET status = CASE status
               WHEN 'PENDING' THEN 'DUE'
               WHEN 'SUBMITTED' THEN 'SUBMITTED'
               WHEN 'ACCEPTED' THEN 'ACCEPTED'
               WHEN 'OVERDUE' THEN 'OVERDUE'
               WHEN 'DUE' THEN 'DUE'
               WHEN 'FEEDBACK_DUE' THEN 'FEEDBACK_DUE'
               ELSE 'DUE'
           END
        """
    ))
    op.alter_column(
        table,
        "status",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="DUE",
    )
    op.create_check_constraint(
        "ck_quality_report_tracker_status",
        table,
        "status IN ('DUE','SUBMITTED','FEEDBACK_DUE','ACCEPTED','OVERDUE')",
    )
    op.alter_column(table, "report_due_date", existing_type=sa.Date(), nullable=False)

    if "fk_quality_report_tracker_created_by" not in _foreign_keys(table):
        op.create_foreign_key(
            "fk_quality_report_tracker_created_by",
            table,
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _drop_index("ix_quality_report_trackers_status_due", table)
    _create_index("ix_quality_report_tracker_status_due", table, ["amo_id", "status", "report_due_date"])
    _create_index("ix_quality_audit_report_trackers_report_due_date", table, ["report_due_date"])
    _create_index("ix_quality_audit_report_trackers_report_submitted_at", table, ["report_submitted_at"])
    _create_index("ix_quality_audit_report_trackers_feedback_due_date", table, ["feedback_due_date"])
    _create_index("ix_quality_audit_report_trackers_status", table, ["status"])
    _create_index("ix_quality_audit_report_trackers_created_by_user_id", table, ["created_by_user_id"])


def _reconcile_reminder_milestones() -> None:
    table = "quality_reminder_milestones"
    if not _has_table(table):
        return

    columns = _columns(table)
    if "recipient_user_id" not in columns:
        op.add_column(table, sa.Column("recipient_user_id", sa.String(length=36), nullable=True))
    if "scheduled_for" not in columns:
        op.add_column(table, sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
    if "due_date" not in columns:
        op.add_column(table, sa.Column("due_date", sa.Date(), nullable=True))
    if "escalated_at" not in columns:
        op.add_column(table, sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    if "severity" not in columns:
        op.add_column(table, sa.Column("severity", sa.String(length=32), nullable=True, server_default="ACTION_REQUIRED"))
    if "message" not in columns:
        op.add_column(table, sa.Column("message", sa.Text(), nullable=True))

    columns = _columns(table)
    if "due_at" in columns:
        op.execute(sa.text(
            """
            UPDATE quality_reminder_milestones
               SET scheduled_for = COALESCE(scheduled_for, due_at, created_at, NOW()),
                   due_date = COALESCE(due_date, due_at::date),
                   severity = COALESCE(NULLIF(severity, ''), 'ACTION_REQUIRED'),
                   message = COALESCE(NULLIF(BTRIM(message), ''), 'Quality workflow reminder: ' || milestone_key)
             WHERE scheduled_for IS NULL
                OR severity IS NULL OR severity = ''
                OR message IS NULL OR BTRIM(message) = ''
            """
        ))
    else:
        op.execute(sa.text(
            """
            UPDATE quality_reminder_milestones
               SET scheduled_for = COALESCE(scheduled_for, created_at, NOW()),
                   severity = COALESCE(NULLIF(severity, ''), 'ACTION_REQUIRED'),
                   message = COALESCE(NULLIF(BTRIM(message), ''), 'Quality workflow reminder: ' || milestone_key)
             WHERE scheduled_for IS NULL
                OR severity IS NULL OR severity = ''
                OR message IS NULL OR BTRIM(message) = ''
            """
        ))

    op.alter_column(table, "scheduled_for", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column(table, "severity", existing_type=sa.String(length=32), nullable=False, server_default="ACTION_REQUIRED")
    op.alter_column(table, "message", existing_type=sa.Text(), nullable=False, server_default=None)

    if "fk_quality_reminder_recipient" not in _foreign_keys(table):
        op.create_foreign_key(
            "fk_quality_reminder_recipient",
            table,
            "users",
            ["recipient_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # The historical unique constraint prevented one governed milestone from
    # being materialised for multiple recipients. The current model deliberately
    # permits recipient-specific rows and uses indexes instead.
    _drop_unique("uq_quality_reminder_milestone", table)
    _create_index("ix_quality_reminder_entity_key", table, ["amo_id", "entity_type", "entity_id", "milestone_key"])
    _create_index("ix_quality_reminder_due_unsent", table, ["amo_id", "scheduled_for", "sent_at"])
    _create_index("ix_quality_reminder_milestones_recipient_user_id", table, ["recipient_user_id"])
    _create_index("ix_quality_reminder_milestones_scheduled_for", table, ["scheduled_for"])
    _create_index("ix_quality_reminder_milestones_due_date", table, ["due_date"])
    _create_index("ix_quality_reminder_milestones_escalated_at", table, ["escalated_at"])


def _reconcile_archive_packages() -> None:
    table = "quality_archive_packages"
    if not _has_table(table):
        return

    columns = _columns(table)
    if "status" not in columns:
        op.add_column(table, sa.Column("status", sa.String(length=32), nullable=True, server_default="READY"))
    if "file_ref" not in columns:
        op.add_column(table, sa.Column("file_ref", sa.String(length=512), nullable=True))
    if "metrics_snapshot_json" not in columns:
        op.add_column(table, sa.Column("metrics_snapshot_json", sa.Text(), nullable=True, server_default="{}"))
    if "generated_by_user_id" not in columns:
        op.add_column(table, sa.Column("generated_by_user_id", sa.String(length=36), nullable=True))
    if "generated_at" not in columns:
        op.add_column(table, sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))

    columns = _columns(table)
    file_source = "storage_ref" if "storage_ref" in columns else "NULL"
    metrics_source = "manifest_json" if "manifest_json" in columns else "NULL"
    actor_source = "created_by_user_id" if "created_by_user_id" in columns else "NULL"
    op.execute(sa.text(
        f"""
        UPDATE quality_archive_packages
           SET status = COALESCE(NULLIF(status, ''), 'READY'),
               file_ref = COALESCE(file_ref, {file_source}),
               metrics_snapshot_json = COALESCE(metrics_snapshot_json, {metrics_source}, '{{}}'),
               generated_by_user_id = COALESCE(generated_by_user_id, {actor_source}),
               generated_at = COALESCE(generated_at, created_at, NOW())
         WHERE status IS NULL OR status = ''
            OR metrics_snapshot_json IS NULL
            OR generated_at IS NULL
        """
    ))

    if "storage_ref" in columns:
        # The active ORM writes file_ref and no longer supplies storage_ref.
        op.alter_column(table, "storage_ref", existing_type=sa.String(length=512), nullable=True)

    op.alter_column(table, "status", existing_type=sa.String(length=32), nullable=False, server_default="READY")
    op.alter_column(table, "metrics_snapshot_json", existing_type=sa.Text(), nullable=False, server_default="{}")
    op.alter_column(table, "generated_at", existing_type=sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())

    if "fk_quality_archive_generated_by" not in _foreign_keys(table):
        op.create_foreign_key(
            "fk_quality_archive_generated_by",
            table,
            "users",
            ["generated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _drop_unique("uq_quality_archive_package_ref", table)
    op.create_unique_constraint(
        "uq_quality_archive_package_ref",
        table,
        ["amo_id", "audit_id", "package_ref"],
    )
    op.create_check_constraint(
        "ck_quality_archive_status",
        table,
        "status IN ('READY','LOCKED','SUPERSEDED')",
    )
    _create_index("ix_quality_archive_audit_generated", table, ["audit_id", "generated_at"])
    _create_index("ix_quality_archive_packages_package_ref", table, ["package_ref"])
    _create_index("ix_quality_archive_packages_status", table, ["status"])
    _create_index("ix_quality_archive_packages_generated_by_user_id", table, ["generated_by_user_id"])


def upgrade() -> None:
    _reconcile_post_briefs()
    _reconcile_report_trackers()
    _reconcile_reminder_milestones()
    _reconcile_archive_packages()


def downgrade() -> None:
    # Archive package: restore the historical storage contract before removing
    # the fields introduced by this reconciliation.
    table = "quality_archive_packages"
    if _has_table(table):
        columns = _columns(table)
        if "storage_ref" in columns and "file_ref" in columns:
            op.execute(sa.text(
                """
                UPDATE quality_archive_packages
                   SET storage_ref = COALESCE(storage_ref, file_ref, 'archive://downgrade/' || id::text)
                 WHERE storage_ref IS NULL
                """
            ))
            op.alter_column(table, "storage_ref", existing_type=sa.String(length=512), nullable=False)
        _drop_check("ck_quality_archive_status", table)
        _drop_unique("uq_quality_archive_package_ref", table)
        op.create_unique_constraint("uq_quality_archive_package_ref", table, ["amo_id", "package_ref"])
        for index_name in (
            "ix_quality_archive_audit_generated",
            "ix_quality_archive_packages_package_ref",
            "ix_quality_archive_packages_status",
            "ix_quality_archive_packages_generated_by_user_id",
        ):
            _drop_index(index_name, table)
        if "fk_quality_archive_generated_by" in _foreign_keys(table):
            op.drop_constraint("fk_quality_archive_generated_by", table, type_="foreignkey")
        for column in ("generated_at", "generated_by_user_id", "metrics_snapshot_json", "file_ref", "status"):
            if column in _columns(table):
                op.drop_column(table, column)

    table = "quality_reminder_milestones"
    if _has_table(table):
        for index_name in (
            "ix_quality_reminder_entity_key",
            "ix_quality_reminder_due_unsent",
            "ix_quality_reminder_milestones_recipient_user_id",
            "ix_quality_reminder_milestones_scheduled_for",
            "ix_quality_reminder_milestones_due_date",
            "ix_quality_reminder_milestones_escalated_at",
        ):
            _drop_index(index_name, table)
        if "fk_quality_reminder_recipient" in _foreign_keys(table):
            op.drop_constraint("fk_quality_reminder_recipient", table, type_="foreignkey")
        for column in ("message", "severity", "escalated_at", "due_date", "scheduled_for", "recipient_user_id"):
            if column in _columns(table):
                op.drop_column(table, column)
        if "uq_quality_reminder_milestone" not in _unique_constraints(table):
            op.create_unique_constraint(
                "uq_quality_reminder_milestone",
                table,
                ["amo_id", "entity_type", "entity_id", "milestone_key"],
            )

    table = "quality_audit_report_trackers"
    if _has_table(table):
        _drop_check("ck_quality_report_tracker_status", table)
        op.execute(sa.text(
            """
            UPDATE quality_audit_report_trackers
               SET status = CASE status
                   WHEN 'DUE' THEN 'PENDING'
                   WHEN 'FEEDBACK_DUE' THEN 'SUBMITTED'
                   ELSE status
               END,
                   due_date = COALESCE(due_date, report_due_date)
            """
        ))
        op.alter_column(table, "status", existing_type=sa.String(length=32), nullable=False, server_default="PENDING")
        if "due_date" in _columns(table):
            op.alter_column(table, "due_date", existing_type=sa.Date(), nullable=False)
        op.create_check_constraint(
            "ck_quality_report_tracker_status",
            table,
            "status IN ('PENDING','SUBMITTED','ACCEPTED','OVERDUE')",
        )
        for index_name in (
            "ix_quality_report_tracker_status_due",
            "ix_quality_audit_report_trackers_report_due_date",
            "ix_quality_audit_report_trackers_report_submitted_at",
            "ix_quality_audit_report_trackers_feedback_due_date",
            "ix_quality_audit_report_trackers_status",
            "ix_quality_audit_report_trackers_created_by_user_id",
        ):
            _drop_index(index_name, table)
        _create_index("ix_quality_report_trackers_status_due", table, ["status", "due_date"])
        if "fk_quality_report_tracker_created_by" in _foreign_keys(table):
            op.drop_constraint("fk_quality_report_tracker_created_by", table, type_="foreignkey")
        for column in ("created_by_user_id", "feedback_submitted_at", "feedback_due_date", "report_due_date"):
            if column in _columns(table):
                op.drop_column(table, column)

    table = "quality_audit_post_briefs"
    if _has_table(table):
        columns = _columns(table)
        if "brief_date" in columns and "briefing_at" in columns:
            op.execute(sa.text(
                """
                UPDATE quality_audit_post_briefs
                   SET brief_date = COALESCE(brief_date, briefing_at::date, created_at::date, CURRENT_DATE)
                 WHERE brief_date IS NULL
                """
            ))
            op.alter_column(table, "brief_date", existing_type=sa.Date(), nullable=False)
        if "summary" in columns:
            op.alter_column(table, "summary", existing_type=sa.Text(), nullable=True)
        _drop_index("ix_quality_audit_post_briefs_audit_id", table)
        _create_index("ix_quality_audit_post_briefs_audit_id", table, ["audit_id"])
        _drop_index("ix_quality_audit_post_briefs_report_due_date", table)
        _drop_index("ix_quality_audit_post_briefs_created_by_user_id", table)
        for column in ("report_due_date", "briefing_at"):
            if column in _columns(table):
                op.drop_column(table, column)
